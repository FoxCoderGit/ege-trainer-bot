"""One card model, native Rich Messages + readable HTML accessibility fallback."""
from dataclasses import dataclass, field
from html import escape
import logging
from .telegram import TelegramError, strip_icons

log = logging.getLogger(__name__)


@dataclass
class Card:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    formula: str = ''
    plain_formula: str = ''
    footer: str = ''
    table: list[list[str]] = field(default_factory=list)

    def blocks(self):
        result = [{'type':'heading','size':3,'text':self.title}]
        result += [{'type':'paragraph','text':p} for p in self.paragraphs[:1]]
        if self.formula:
            result.append({'type':'mathematical_expression','expression':self.formula})
        if self.table:
            rows = [' & '.join('?' if c == '—' else c for c in row) for row in self.table]
            expression = r'\begin{array}{ccccc}' + r' \\ '.join(rows) + r'\end{array}'
            result.append({'type':'mathematical_expression','expression':expression})
        result += [{'type':'paragraph','text':p} for p in self.paragraphs[1:]]
        if self.footer:
            result.append({'type':'footer','text':self.footer})
        return result

    def html(self):
        parts = ['<b>'+escape(self.title)+'</b>'] + [escape(p) for p in self.paragraphs[:1]]
        if self.plain_formula:
            parts.append('<code>'+escape(self.plain_formula)+'</code>')
        if self.table:
            parts.append('<pre>'+escape('\n'.join('  '.join(row) for row in self.table))+'</pre>')
        parts.extend(escape(p) for p in self.paragraphs[1:])
        if self.footer:
            parts.append('<i>'+escape(self.footer)+'</i>')
        return '\n\n'.join(parts)


def button(label, action, style=None, icon=None):
    result = {'text':label,'callback_data':action}
    if style:
        result['style']=style
    if icon:
        result['icon_custom_emoji_id']=icon
    return result


class UI:
    def __init__(self, api, db):
        self.api, self.db = api, db

    def show(self, uid, card, rows, fresh=False):
        user=self.db.user(uid)
        revision=user['revision']+1
        keyboard={'inline_keyboard': [[{**b,'callback_data':f'{revision}:{b["callback_data"]}'} for b in row] for row in rows]}
        assert all(len(b['callback_data'].encode())<=64 for row in keyboard['inline_keyboard'] for b in row)
        self.db.set_user(uid, revision=revision)
        rich = user['rendering']=='rich' and self.db.meta('rich_unsupported')!='1'
        mid = None if fresh else user['card_id']
        # Retire old buttons when moving the working card to the bottom of the chat.
        if fresh and user['card_id']:
            try:
                self.api.call('editMessageReplyMarkup',chat_id=uid,message_id=user['card_id'],reply_markup={'inline_keyboard':[]})
            except TelegramError as exc:
                if exc.code not in (400,403):
                    log.warning('Could not retire previous card: %s', exc.code)
        for _ in range(4):
            payload={'chat_id':uid,'reply_markup':keyboard}
            if rich:
                payload['rich_message']={'blocks':card.blocks()}
            else:
                payload.update(text=card.html(),parse_mode='HTML')
            if mid:
                payload['message_id']=mid
                method='editMessageText'
            else:
                method='sendRichMessage' if rich else 'sendMessage'
            try:
                message=self.api.call(method,**payload)
                if isinstance(message,dict):
                    self.db.set_user(uid,card_id=message['message_id'])
                return
            except TelegramError as exc:
                desc=exc.description.lower()
                if exc.code==400 and 'message is not modified' in desc:
                    return
                if exc.code==400 and ('custom emoji' in desc or 'custom_emoji' in desc or 'button style' in desc):
                    keyboard=strip_icons(keyboard)
                    log.warning('Decoration rejected; retrying with plain buttons')
                    continue
                if mid and exc.code==400 and any(t in desc for t in ('message to edit not found',"message can't be edited",'message_id_invalid')):
                    mid=None
                    continue
                if rich and ((exc.code==404 and method=='sendRichMessage') or (exc.code==400 and any(t in desc for t in ('rich_message','rich message','mathematical_expression','not supported')))):
                    rich=False
                    self.db.set_user(uid,rendering='plain')
                    if exc.code==404:
                        self.db.set_meta('rich_unsupported','1')
                    log.warning('Rich rendering rejected; using readable plain mode')
                    continue
                raise
        raise TelegramError(400,'Could not render card')

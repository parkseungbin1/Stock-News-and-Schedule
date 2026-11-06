"""
텔레그램 봇을 통한 메시지 전송
"""
import logging
from telegram import Bot
from telegram.error import TelegramError
import asyncio

logger = logging.getLogger(__name__)


class TelegramSender:
    """텔레그램 봇을 통한 메시지 전송 클래스"""
    
    def __init__(self, bot_token, chat_id):
        """
        초기화
        
        Args:
            bot_token (str): 텔레그램 봇 토큰
            chat_id (str): 텔레그램 채팅 ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = Bot(token=bot_token)
    
    async def send_message(self, message, parse_mode='HTML'):
        """
        텔레그램으로 메시지 전송
        
        Args:
            message (str): 전송할 메시지
            parse_mode (str): 메시지 형식 (HTML, Markdown)
        
        Returns:
            bool: 성공 여부
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.info("텔레그램 메시지 전송 성공")
            return True
        except TelegramError as e:
            logger.error(f"텔레그램 메시지 전송 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")
            return False
    
    def send_message_sync(self, message, parse_mode='HTML'):
        """
        동기식으로 텔레그램 메시지 전송 (HTTPS 직접 전송으로 윈도우 비동기 타임아웃 방지)
        
        Args:
            message (str): 전송할 메시지
            parse_mode (str): 메시지 형식
        
        Returns:
            bool: 성공 여부
        """
        import json
        import urllib.request
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True
        }
        data = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                if res_data.get('ok'):
                    logger.info("텔레그램 메시지 전송 성공")
                    return True
        except Exception as e:
            logger.warning(f"HTTPS 직접 전송 실패 ({e}), 비동기 폴백 시도...")

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.send_message(message, parse_mode))
            return result
        except Exception as e:
            logger.error(f"동기식 메시지 전송 오류: {e}")
            return False
        finally:
            loop.close()


async def send_economic_calendar_to_telegram(message, bot_token, chat_id):
    """
    경제 캘린더 메시지를 텔레그램으로 전송
    
    Args:
        message (str): 전송할 메시지
        bot_token (str): 텔레그램 봇 토큰
        chat_id (str): 텔레그램 채팅 ID
    
    Returns:
        bool: 성공 여부
    """
    sender = TelegramSender(bot_token, chat_id)
    return await sender.send_message(message, parse_mode='HTML')


def send_economic_calendar_to_telegram_sync(message, bot_token, chat_id):
    """
    동기식 경제 캘린더 메시지 전송
    
    Args:
        message (str): 전송할 메시지
        bot_token (str): 텔레그램 봇 토큰
        chat_id (str): 텔레그램 채팅 ID
    
    Returns:
        bool: 성공 여부
    """
    sender = TelegramSender(bot_token, chat_id)
    return sender.send_message_sync(message, parse_mode='HTML')

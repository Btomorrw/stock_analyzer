# notifier.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import logging
from config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER,
    SMTP_SERVER, SMTP_PORT,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)

logger = logging.getLogger(__name__)


class Notifier:
    """알림 전송 클래스"""

    def send_email(self, subject: str, body: str) -> bool:
        """이메일 전송"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = EMAIL_SENDER
            msg["To"] = EMAIL_RECEIVER

            # 마크다운 → 간단한 HTML 변환
            html_body = self._markdown_to_html(body)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(msg)

            logger.info(f"✅ 이메일 전송 성공: {subject}")
            return True

        except Exception as e:
            logger.error(f"❌ 이메일 전송 실패: {e}")
            return False

    def send_telegram(self, message: str) -> bool:
        """텔레그램 메시지 전송"""
        try:
            # 텔레그램 메시지 길이 제한 (4096자)
            chunks = self._split_message(message, 4000)

            for chunk in chunks:
                url = (
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
                    f"/sendMessage"
                )
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                }
                response = requests.post(url, json=payload, timeout=10)

                if response.status_code != 200:
                    # Markdown 파싱 실패 시 일반 텍스트로 재시도
                    payload.pop("parse_mode", None)
                    requests.post(url, json=payload, timeout=10)

            logger.info("✅ 텔레그램 전송 성공")
            return True

        except Exception as e:
            logger.error(f"❌ 텔레그램 전송 실패: {e}")
            return False

    def send_all(self, subject: str, body: str):
        """이메일 + 텔레그램 동시 전송"""
        self.send_email(subject, body)
        self.send_telegram(f"*{subject}*\n\n{body}")

    def _split_message(self, text: str, max_len: int) -> list:
        """긴 메시지를 분할"""
        if len(text) <= max_len:
            return [text]

        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break

            # 줄바꿈 기준으로 자르기
            split_idx = text.rfind("\n", 0, max_len)
            if split_idx == -1:
                split_idx = max_len

            chunks.append(text[:split_idx])
            text = text[split_idx:].lstrip()

        return chunks

    def _markdown_to_html(self, md_text: str) -> str:
        """간단한 마크다운 → HTML 변환"""
        html = md_text
        html = html.replace("\n", "<br>")

        # 간단한 변환 (완벽하지 않지만 이메일용으로 충분)
        import re
        # 주의: ### 를 ## 보다 먼저 매칭해야 올바르게 변환됨
        html = re.sub(r"### (.*?)<br>", r"<h3>\1</h3>", html)
        html = re.sub(r"## (.*?)<br>", r"<h2>\1</h2>", html)
        html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)

        return f"""
        <html><body style="font-family: 'Malgun Gothic', sans-serif;
        line-height: 1.6; padding: 20px;">
        {html}
        </body></html>
        """


if __name__ == "__main__":
    notifier = Notifier()
    notifier.send_telegram("🧪 테스트 메시지\n시스템이 정상 작동합니다.")

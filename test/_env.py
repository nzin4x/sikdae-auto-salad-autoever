"""로컬 테스트 스크립트 공용: .env(gitignore)에서 자격증명을 읽는다.

파일명 앞에 언더스코어를 붙여 pytest가 테스트 모듈로 수집하지 않도록 했다.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def mealc_credentials() -> tuple[str, str]:
    user_id = os.environ.get("MEALC_USER_ID")
    password = os.environ.get("MEALC_PASSWORD")
    if not user_id or not password:
        raise SystemExit(
            f"{ROOT / '.env'} 에 MEALC_USER_ID/MEALC_PASSWORD가 없습니다. .env.example을 복사해서 채워주세요."
        )
    return user_id, password

"""DynamoDB(단일 테이블) 기반 sikdae-auto 회원 설정 저장소."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import boto3
from botocore.exceptions import ClientError

from .crypto import decrypt, encrypt
from .models import UserPreferences

LOGGER = logging.getLogger()


class ConfigStore:
    def __init__(self, table_name: Optional[str] = None, region_name: Optional[str] = None, dynamodb_resource=None) -> None:
        self.table_name = table_name or os.environ.get("CONFIG_TABLE_NAME")
        if not self.table_name:
            raise ValueError("CONFIG_TABLE_NAME env var is required")

        endpoint_url = os.environ.get("DYNAMODB_ENDPOINT_URL")
        if endpoint_url:
            self._dynamodb = dynamodb_resource or boto3.resource("dynamodb", region_name=region_name, endpoint_url=endpoint_url)
        else:
            self._dynamodb = dynamodb_resource or boto3.resource("dynamodb", region_name=region_name)
        self._table = self._dynamodb.Table(self.table_name)

    # ---- 회원 설정(PK=USER#{email}, SK=CONFIG) ----

    def get_user_preferences(self, email: str) -> UserPreferences:
        item = self._get_config_item(email)
        if not item:
            raise KeyError(f"Config not found for {email}")

        return UserPreferences(
            email=email,
            mealc_user_id=item["mealcUserId"],
            mealc_password=decrypt(item["mealcPasswordEncrypted"]),
            menu_preference=list(item.get("menuPreference", [])),
            delivery_spot_keyword=item.get("deliverySpotKeyword", ""),
            store_id=item.get("storeId"),
            exclusion_dates=list(item.get("exclusionDates", [])),
            is_active=item.get("isActive", True),
            notification_emails=list(item.get("notificationEmails", [])),
            last_reserved_date=item.get("lastReservedDate"),
        )

    def save_user_preferences(self, prefs: UserPreferences) -> None:
        item = {
            "PK": f"USER#{prefs.email}",
            "SK": "CONFIG",
            "email": prefs.email,
            "mealcUserId": prefs.mealc_user_id,
            "mealcPasswordEncrypted": encrypt(prefs.mealc_password),
            "menuPreference": prefs.menu_preference,
            "deliverySpotKeyword": prefs.delivery_spot_keyword,
            "exclusionDates": prefs.exclusion_dates,
            "isActive": prefs.is_active,
            "notificationEmails": prefs.notification_emails,
        }
        if prefs.store_id:
            item["storeId"] = prefs.store_id
        if prefs.last_reserved_date:
            item["lastReservedDate"] = prefs.last_reserved_date
        try:
            self._table.put_item(Item=item)
        except ClientError as error:
            raise RuntimeError(f"Failed to save config for {prefs.email}: {error}") from error

    def profile_exists(self, email: str) -> bool:
        return self._get_config_item(email) is not None

    def list_active_users(self) -> List[str]:
        return [
            item["email"]
            for item in self._scan_config_items()
            if item.get("isActive", True)
        ]

    def count_users(self) -> int:
        return len(self._scan_config_items())

    def update_auto_reservation_status(self, email: str, enabled: bool) -> None:
        self._update_config(email, "SET isActive = :v", {":v": enabled})

    def update_exclusion_dates(self, email: str, dates: List[str]) -> None:
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        filtered = [d for d in dates if d >= cutoff]
        self._update_config(email, "SET exclusionDates = :v", {":v": filtered})

    def update_last_reserved_date(self, email: str, date_str: str) -> None:
        self._update_config(email, "SET lastReservedDate = :v", {":v": date_str})

    def update_user_settings(
        self,
        email: str,
        menu_preference: Optional[List[str]] = None,
        delivery_spot_keyword: Optional[str] = None,
        mealc_user_id: Optional[str] = None,
        mealc_password: Optional[str] = None,
        notification_emails: Optional[List[str]] = None,
    ) -> None:
        parts = []
        values: Dict[str, Any] = {}
        if menu_preference is not None:
            parts.append("menuPreference = :menuPreference")
            values[":menuPreference"] = menu_preference
        if delivery_spot_keyword is not None:
            parts.append("deliverySpotKeyword = :deliverySpotKeyword")
            values[":deliverySpotKeyword"] = delivery_spot_keyword
        if mealc_user_id is not None:
            parts.append("mealcUserId = :mealcUserId")
            values[":mealcUserId"] = mealc_user_id
        if mealc_password is not None:
            parts.append("mealcPasswordEncrypted = :mealcPasswordEncrypted")
            values[":mealcPasswordEncrypted"] = encrypt(mealc_password)
        if notification_emails is not None:
            parts.append("notificationEmails = :notificationEmails")
            values[":notificationEmails"] = notification_emails
        if not parts:
            return
        self._update_config(email, "SET " + ", ".join(parts), values)

    def delete_profile(self, email: str) -> None:
        try:
            response = self._table.query(
                KeyConditionExpression="PK = :pk", ExpressionAttributeValues={":pk": f"USER#{email}"}
            )
            for item in response.get("Items", []):
                self._table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        except ClientError as error:
            raise RuntimeError(f"Failed to delete config for {email}: {error}") from error

    # ---- 디바이스 자동로그인(PK=USER#{email}, SK=DEVICE#{fingerprint}) ----

    def register_device(self, email: str, fingerprint: str) -> None:
        now = datetime.utcnow().isoformat()
        self._table.put_item(
            Item={
                "PK": f"USER#{email}",
                "SK": f"DEVICE#{fingerprint}",
                "fingerprint": fingerprint,
                "registeredAt": now,
                "lastAccessAt": now,
            }
        )

    def find_user_by_device(self, fingerprint: str) -> Optional[str]:
        response = self._table.scan(
            FilterExpression="SK = :sk",
            ExpressionAttributeValues={":sk": f"DEVICE#{fingerprint}"},
        )
        items = response.get("Items", [])
        if not items:
            return None
        return items[0]["PK"].removeprefix("USER#")

    def update_device_access(self, email: str, fingerprint: str) -> None:
        self._table.update_item(
            Key={"PK": f"USER#{email}", "SK": f"DEVICE#{fingerprint}"},
            UpdateExpression="SET lastAccessAt = :now",
            ExpressionAttributeValues={":now": datetime.utcnow().isoformat()},
        )

    def remove_device(self, email: str, fingerprint: str) -> bool:
        try:
            response = self._table.delete_item(
                Key={"PK": f"USER#{email}", "SK": f"DEVICE#{fingerprint}"},
                ReturnValues="ALL_OLD",
            )
        except ClientError as error:
            raise RuntimeError(f"Failed to remove device for {email}: {error}") from error
        return "Attributes" in response

    # ---- 이메일 인증코드(PK=VERIFY#{email}, SK=CODE) ----

    def save_verification_code(self, email: str, code: str, ttl_minutes: int = 10) -> None:
        expires_at = int((datetime.utcnow() + timedelta(minutes=ttl_minutes)).timestamp())
        self._table.put_item(
            Item={"PK": f"VERIFY#{email}", "SK": "CODE", "code": code, "expiresAt": expires_at}
        )

    def get_verification_code(self, email: str) -> Optional[Dict[str, Any]]:
        response = self._table.get_item(Key={"PK": f"VERIFY#{email}", "SK": "CODE"})
        return response.get("Item")

    def delete_verification_code(self, email: str) -> None:
        self._table.delete_item(Key={"PK": f"VERIFY#{email}", "SK": "CODE"})

    # ---- 공휴일 캐시(PK=COMMON, SK=HOLIDAY#{YYYYMM}) ----

    def save_holidays(self, year: int, month: int, dates: Set[str]) -> None:
        self._table.put_item(
            Item={
                "PK": "COMMON",
                "SK": f"HOLIDAY#{year}{month:02d}",
                "dates": list(dates) if dates else [],
                "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
            }
        )

    def get_holidays(self, year: int, month: int) -> Optional[Set[str]]:
        response = self._table.get_item(Key={"PK": "COMMON", "SK": f"HOLIDAY#{year}{month:02d}"})
        item = response.get("Item")
        if not item:
            return None
        return set(item.get("dates", []))

    # ---- 내부 헬퍼 ----

    def _get_config_item(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            response = self._table.get_item(Key={"PK": f"USER#{email}", "SK": "CONFIG"})
        except ClientError as error:
            raise RuntimeError(f"Failed to load config for {email}: {error}") from error
        return response.get("Item")

    def _scan_config_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        kwargs = {"FilterExpression": "SK = :sk", "ExpressionAttributeValues": {":sk": "CONFIG"}}
        response = self._table.scan(**kwargs)
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = self._table.scan(ExclusiveStartKey=response["LastEvaluatedKey"], **kwargs)
            items.extend(response.get("Items", []))
        return items

    def _update_config(self, email: str, update_expression: str, values: Dict[str, Any]) -> None:
        try:
            self._table.update_item(
                Key={"PK": f"USER#{email}", "SK": "CONFIG"},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=values,
            )
        except ClientError as error:
            raise RuntimeError(f"Failed to update config for {email}: {error}") from error

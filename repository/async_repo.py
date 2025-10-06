import json
from types import NoneType
from supabase import Client
from zoneinfo import ZoneInfo
from datetime import date, time, timedelta, datetime, timezone

VALID_EVENT_TYPES = {"new_customer", "returning_customer"}

def _get_time_vn() -> str:
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)

    now_vn = now_vn.replace(microsecond=0)
    now_vn.strftime("%Y-%m-%d %H:%M:%S+07")
    
    return now_vn

def _to_vn(dt_str_or_dt) -> str:
        if isinstance(dt_str_or_dt, str):
            # parse chuỗi ISO (UTC)
            dt = datetime.fromisoformat(dt_str_or_dt)
        else:
            dt = dt_str_or_dt
        # nếu dt không có tzinfo, giả sử là UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # chuyển sang giờ VN
        dt_vn = dt.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        dt_vn = dt_vn.strftime("%Y-%m-%d %H:%M:%S+07")
        
        return dt_vn

class AsyncCustomerRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    async def get_uuid(self, chat_id: str) -> str | None:
        response = (
            self.supabase_client.table("customers")
                .select("uuid")
                .eq("chat_id", chat_id)
                .execute()
        )

        return response.data[0]["uuid"] if response.data else None
    
    async def get_or_create_customer(self, chat_id: str) -> dict | None:
        response = (
            self.supabase_client.table("customers")
            .upsert(
                {"chat_id": chat_id},
                on_conflict="chat_id"
            )
            .execute()
        )

        return response.data[0] if response.data else None

    async def delete_customer(self, chat_id: str) -> bool:
        response = (
            self.supabase_client.table("customers")
            .delete()
            .eq("chat_id", chat_id)
            .execute()
        )
        return bool(response.data)
    
    async def update_uuid(self, chat_id: str, new_uuid: str) -> str | None:
        response = (
            self.supabase_client.table("customers")
            .update({"uuid": new_uuid})
            .eq("chat_id", chat_id)
            .execute()
        )

        return response.data[0]["uuid"] if response.data else None
    
    async def find_customer(self, chat_id: str) -> dict | None:
        response = (
            self.supabase_client.table("customers")
            .select("*, sessions(*)")
            .eq("chat_id", chat_id)
            .eq("sessions.status", "active")
            .execute()
        )

        if not response.data:
            return None
        
        session = response.data[0]["sessions"][0]
        session["started_at"] = _to_vn(session["started_at"]) 
        session["last_active_at"] = _to_vn(session["last_active_at"]) 
        
        return response.data[0]
    
    async def create_customer(self, chat_id: str) -> dict | None:
        response = (
            self.supabase_client.table("customers")
            .insert({"chat_id": chat_id})
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def create_session(self, customer_id: str, thread_id: str) -> dict | None:
        response = (
            self.supabase_client.table("sessions")
            .insert(
                {
                    "customer_id": customer_id,
                    "thread_id": thread_id,
                    "started_at": _get_time_vn(),
                    "last_active_at": _get_time_vn(),
                    "status": "active"
                }
            )
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def update_end_session(self, session_id: int) -> dict | None:
        response = (
            self.supabase_client.table("sessions")
            .update(
                {
                    "status": "inactive",
                    "ended_at": _get_time_vn()
                }
            )
            .eq("id", session_id)
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def create_event(self, customer_id: int, session_id: int, event_type: str) -> str | None:
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}. Must be one of {VALID_EVENT_TYPES}")

        response = (
            self.supabase_client.table("events")
            .insert(
                {
                    "customer_id": customer_id,
                    "session_id": session_id,
                    "event_type": event_type,
                    "timestamp": _get_time_vn()
                }
            )
            .execute()
        )
        
        return response.data[0] if response.data else None
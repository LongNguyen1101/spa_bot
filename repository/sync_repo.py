from datetime import date, time, timedelta, datetime
import json
from supabase import Client
from log.logger_config import setup_logging

logger = setup_logging(__name__)

class CustomerRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def create_customer(self, chat_id: str) -> dict | None:
        response = (
            self.supabase_client.table("customer")
            .insert({"chat_id": chat_id})
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def get_customer_by_chat_id(
        self, 
        chat_id: str
    ) -> dict | None:
        response = (
            self.supabase_client.table("customer")
            .select("*")
            .eq("chat_id", chat_id)
            .execute()
        )

        return response.data[0] if response.data else None
    
    def get_or_create_customer(self, chat_id: str) -> dict | None:
        response = (
            self.supabase_client.table("customers")
            .upsert(
                {"chat_id": chat_id},
                on_conflict="chat_id"
            )
            .execute()
        )

        return response.data[0] if response.data else None
    
    def check_customer_id(self, customer_id: int) -> bool:
        response = (
            self.supabase_client.table('customers')
            .select('id')
            .eq("id", customer_id)
            .execute()
        )
        
        return True if response.data else False
    
    def update_customer_by_customer_id(
        self, 
        update_payload: dict, 
        customer_id: int
    ) -> dict | None:
        response = (
            self.supabase_client.table('customers')
            .update(update_payload)
            .eq('id', customer_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def update_customer_by_chat_id(
        self, 
        update_payload: dict, 
        chat_id: str
    ) -> dict | None:
        response = (
            self.supabase_client.table('customers')
            .update(update_payload)
            .eq('chat_id', chat_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def get_uuid(self, chat_id: str) -> str | None:
        res = (
            self.supabase_client.table("customers")
                .select("uuid")
                .eq("chat_id", chat_id)
                .execute()
        )

        return res.data[0]["uuid"] if res.data else None
    
class ServiceRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def get_service_by_keyword(self, keyword: str) -> list[dict] | None:
        pattern = f"%{keyword}%"

        response = (
            self.supabase_client
            .from_("services")
            .select("*")
            .or_(f"name.ilike.{pattern},description.ilike.{pattern},type.ilike.{pattern}")
            .execute()
        )
        
        return response.data if response.data else None
    
    def get_services_by_embedding(
        self, 
        query_embedding: list[float],
        match_count: int = 5
    ) -> list[dict] | None:
        response = self.supabase_client.rpc(
            "match_services_embedding",
            {
                "query_embedding": query_embedding, 
                "match_count": match_count,
                "filter": {}
            }
        ).execute()
        
        if not response.data:
            return None

        results = [
            {
                "similarity": data["similarity"],
                "content": json.loads(data['content'])
            }
            for data in response.data
        ]
        
        return results
    
    def get_qna_by_embedding(
        self, 
        query_embedding: list[float], 
        match_count: int = 3
    ) -> list[dict] | None:
        response = self.supabase_client.rpc(
            "match_qna",
            {
                "query_embedding_input": query_embedding,
                "match_count": match_count
            }
        ).execute()
        
        return response.data if response.data else None
    
    def get_all_services_without_des(self) -> list[dict]:
        response = (
            self.supabase_client
            .table("services")
            .select("id, type, name, duration_minutes, price")
            .order("type")
            .execute()
        )
        
        return response.data if response.data else None
    
    
class RoomRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def get_all_rooms(self) -> list[dict] | None:
        response = (
            self.supabase_client.table('rooms')
            .select("id", "capacity")
            .execute()
        )
        
        return response.data if response.data else None
    
    def get_all_rooms_return_dict(self) -> dict | None:
        response = (
            self.supabase_client.table('rooms')
            .select("id", "name", "capacity")
            .execute()
        )
        
        if not response.data:
            return None
        
        rooms_dict = {}
        for data in response.data:
            rooms_dict[data["id"]] = {
                "name": data["name"],
                "capacity": data["capacity"]
            }
        
        return rooms_dict
    
    
class AppointmentRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def get_overlap_appointments(
        self, 
        booking_date_new: date, 
        start_time_new: time,
        end_time_new: time,
        buffer_time: int = 5
    ) -> list[dict]:
        # booking_date_new = datetime.strptime(booking_date_new, "%Y-%m-%d").date()
        # start_time_new = datetime.strptime(start_time_new, "%H:%M:%S").time()
        # end_time_new = datetime.strptime(end_time_new, "%H:%M:%S").time()
        buffer = timedelta(minutes=buffer_time)
        
         # Tạo datetime giả để cộng buffer
        dt_start = datetime.combine(booking_date_new, start_time_new)
        dt_end = datetime.combine(booking_date_new, end_time_new)

        # cộng buffer
        dt_start_buffered = dt_start - buffer
        dt_end_buffered = dt_end + buffer

        # lấy lại phần time sau khi buffer
        start_time_threshold = dt_start_buffered.time()
        end_time_threshold = dt_end_buffered.time()
        
        response = (
            self.supabase_client
            .table("appointments")
            .select("*")
            .eq("booking_date", booking_date_new)
            .in_("status", ["booked", "completed"])
            .lt("start_time", end_time_threshold)
            .gt("end_time", start_time_threshold)
            .execute()
        )
        
        return response.data if response.data else None
    
    def create_appointment(self, appointment_payload: dict) -> dict | None:
        response = (
            self.supabase_client.table('appointments')
            .insert(appointment_payload)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def create_appointment_services_item_bulk(self, services_to_insert: list[dict]) -> dict | None:
        response = (
            self.supabase_client.table('appointment_services')
            .insert(services_to_insert)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def get_appointment_details(self, appointment_id: int) -> dict | None:
        response = (
            self.supabase_client
            .table("appointments")
            .select("""
                *,
                appointment_services (
                    services (
                        id,
                        type,
                        name,
                        duration_minutes,
                        price
                    )
                ),
                customer:customers!fk_appointments_customer (
                    id,
                    name,
                    phone,
                    email
                ),
                staff:staffs!fk_appointments_staff (
                    id,
                    name
                ),
                room:rooms!fk_appointments_room (
                    id,
                    name
                )
            """)
            .eq("id", appointment_id)
            .single()
            .execute()
        )

        return response.data if response.data else None
    

class StaffRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def get_all_staff_return_dict(self) -> dict | None:
        response = (
            self.supabase_client.table('staffs')
            .select("id", "name")
            .execute()
        )
        
        if not response.data:
            return None
        
        staff_dict = {}
        for data in response.data:
            staff_dict[data["id"]] = data["name"]
        
        return staff_dict

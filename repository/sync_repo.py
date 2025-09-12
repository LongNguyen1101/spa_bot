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
            self.supabase_client.table("customer")
            .upsert(
                {"chat_id": chat_id},
                on_conflict="chat_id"
            )
            .execute()
        )

        return response.data[0] if response.data else None
    
    def check_customer_id(self, customer_id: int) -> bool:
        response = (
            self.supabase_client.table('customer')
            .select('customer_id')
            .eq("customer_id", customer_id)
            .execute()
        )
        
        return True if response.data else False
    
    def update_customer_by_customer_id(
        self, 
        update_payload: dict, 
        customer_id: int
    ) -> dict | None:
        response = (
            self.supabase_client.table('customer')
            .update(update_payload)
            .eq('customer_id', customer_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def update_customer_by_chat_id(
        self, 
        update_payload: dict, 
        chat_id: str
    ) -> dict | None:
        response = (
            self.supabase_client.table('customer')
            .update(update_payload)
            .eq('chat_id', chat_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def get_uuid(self, chat_id: str) -> str | None:
        res = (
            self.supabase_client.table("customer")
                .select("uuid")
                .eq("chat_id", chat_id)
                .execute()
        )

        return res.data[0]["uuid"] if res.data else None
    
class OrderRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def get_order_details(self, order_id: int) -> dict | None:
        response = (
            self.supabase_client.table("orders")
            .select("""
                *, 
                order_items (
                    item_id,
                    product_des_id,
                    price,
                    quantity,
                    subtotal,
                    products (
                        product_id,
                        sku,
                        product_name,
                        variance_des
                    )
                )
            """)
            .eq("order_id", order_id)
            .single()
            .execute()
        )

        return response.data if response.data else None
        
    def get_all_editable_orders(self, customer_id: int) -> list[dict] | None:

        forbidden = "(delivered,cancelled,returned,refunded)"
        response = (
            self.supabase_client.table("orders")
            .select("""
                *, 
                order_items (
                    item_id,
                    product_des_id,
                    price,
                    quantity,
                    subtotal,
                    products (
                        product_id,
                        sku,
                        product_name,
                        variance_des
                    )
                )
            """)
            .eq("customer_id", customer_id)
            .not_.in_("status", forbidden)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        return response.data if response.data else None
    
    def create_order(self, order_payload: dict) -> dict | None:
        response = (
            self.supabase_client.table('orders')
            .insert(order_payload)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def create_order_item(self, item_to_insert: dict) -> dict | None:
        response = (
            self.supabase_client.table('order_items')
            .insert(item_to_insert)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def create_order_item_bulk(self, items_to_insert: list[dict]) -> dict | None:
        response = (
            self.supabase_client.table('order_items')
            .insert(items_to_insert)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def update_order(self, update_payload: dict, order_id: int) -> dict | None:
        response = (
            self.supabase_client.table('orders')
            .update(update_payload)
            .eq('order_id', order_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def cancel_order(self, order_id: int) -> dict | None:
        response = (
            self.supabase_client.table('orders')
            .update({"status": "cancelled"})
            .eq('order_id', order_id)
            .neq('status', 'cancelled')
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def delete_order_item(self, item_id: int) -> dict | None:
        response = (
            self.supabase_client.table("order_items")
            .delete()
            .eq("item_id", item_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    def update_order_item(
        self, 
        item_id: int, 
        update_payload: dict
    ) -> dict | None:
        response = (
            self.supabase_client.table("order_items")
            .update(update_payload)
            .eq("item_id", item_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
class ProductRepo:
    def __init__(self, supabase_client: Client):
        self.supabase_client = supabase_client
        
    def get_product_by_keyword(self, keyword: str) -> list[dict] | None:
        response = (
            self.supabase_client.from_("products").select("*")
            .ilike('product_name', f'%{keyword}%')
            .limit(5).execute()
        )
        
        return response.data if response.data else None
    
    def get_product_by_embedding(
        self, 
        query_embedding: list[float],
        match_count: int = 5
    ) -> list[dict] | None:
        response = self.supabase_client.rpc(
            "match_product_descriptions",
            {
                "query_embedding_input": query_embedding, 
                "match_count": match_count
            }
        ).execute()
        
        return response.data if response.data else None
    
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
import json
import asyncio

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from langgraph.graph import StateGraph
from openai import chat

from core.graph.state import AgentState, init_state
from core.utils.function import check_state, stream_messages
from repository.sync_repo import CustomerRepo
from database.connection import supabase_client

from log.logger_config import setup_logging

logger = setup_logging(__name__)

customer_repo = CustomerRepo(supabase_client=supabase_client)

async def _handle_normal_chat(
    config: dict,
    state: AgentState,
    graph: StateGraph
):
    try:
        events = graph.astream(state, config=config)

        return events
    
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
        
async def _handle_new_chat(
    chat_id: str,
    graph: StateGraph
):
    try:
        graph.checkpointer.delete_thread(chat_id)
        
        update_customer = customer_repo.update_customer_by_chat_id(
            update_payload={"state": None},
            chat_id=chat_id
        )
        
        if not update_customer:
            logger.error("Lỗi ở cấp DB -> Không thể xoá state")
            error_dict = {"error": "Lỗi không thể xoá state"}
            
            yield f"data: {json.dumps(error_dict, ensure_ascii=False)}\n\n"
        else:
            logger.info("Xoá state thành công")

            response = (
                "Chào khách, em rất vui được hỗ trợ khách. Nếu khách có thắc mắc hoặc "
                "cần tư vấn về các sản phẩm điện tử thông minh của cửa hàng, hãy cho em biết nhé! Em rất sẵn lòng giúp đỡ.\n"
                "(đã reset hoặc tạo mới đoạn chat)."
            )

            msg = {"content": response}
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
        
        
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        error_dict = {"error": str(e), "thread_id": chat_id}
        yield f"data: {json.dumps(error_dict, ensure_ascii=False)}\n\n"
        
    finally:
        await asyncio.sleep(0.01)
        yield "data: [DONE]\n\n"

async def _get_state(
    chat_id: str,
    config: dict,
    graph: StateGraph
):
    try:
        state = await check_state(config=config, graph=graph)

        if not state:
            logger.info("Không tìm thấy state trong langgraph -> truy cập DB")

            customer = customer_repo.get_customer_by_chat_id(chat_id=chat_id)

            if customer:
                logger.info(f"Khách tồn tại, ID là: {customer["customer_id"]}")
                
                if not customer["state"]:
                    state = init_state()
                    
                    state.update({
                        "customer_id": customer["customer_id"],
                        "chat_id": chat_id,
                        "name": customer["name"],
                        "address": customer["address"],
                        "phone_number": customer["phone_number"]
                    })
                else:
                    state = customer["state"]
            else:
                logger.info("Khách không tồn tại")
                new_customer = customer_repo.create_customer(chat_id=chat_id)

                if not new_customer:
                    logger.error("Lỗi ở cấp DB -> Không thể tạo khách")
                    raise
                
                logger.info(f"Tạo mới khách thành công, ID là: {customer["customer_id"]}")
                state = init_state()
                state.update({
                    "customer_id": customer["customer_id"],
                    "chat_id": chat_id
                })

        return state
    except Exception as e:
        logger.info(f"Lỗi: {e}")
        raise
        
async def process_chat(
    user_input: str, 
    chat_id: str,
    graph: StateGraph
) -> StreamingResponse | None:
    try:
        config = {"configurable": {"thread_id": chat_id}}
        
        state = await _get_state(
            chat_id=chat_id,
            config=config,
            graph=graph
        )
        
        if any(cmd in user_input for cmd in ["/start", "/restart"]):
            return StreamingResponse(
                _handle_new_chat(chat_id=chat_id),
                media_type="text/event-stream"
            )
            
        events = await _handle_normal_chat(
            config=config,
            state=state,
            graph=graph
        )

        if events:
            return StreamingResponse(
                stream_messages(events, chat_id),
                media_type="text/event-stream"
            )
        
    except Exception as e:
        logger.info(f"Lỗi: {e}")
        raise HTTPException(status_code=500, detail=e)
        
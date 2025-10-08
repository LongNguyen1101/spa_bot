import os
import traceback
from typing import Literal
from urllib import response
from dotenv import load_dotenv

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from schemas.resquest import ChatRequest
from schemas.response import ChatResponse
from repository.async_repo import AsyncCustomerRepo
from services.v5.process_chat import handle_request
from core.graph.build_graph import create_main_graph

from log.logger_config import setup_logging

load_dotenv()
logger = setup_logging(__name__)

N_DAYS = int(os.getenv("N_DAYS"))

router = APIRouter()
graph = create_main_graph()
async_customer_repo = AsyncCustomerRepo()


@router.post("/chat/invoke", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse | HTTPException:
    chat_id = request.chat_id
    user_input = request.user_input
    
    try:    
        response = await handle_request(
            chat_id=chat_id,
            user_input=user_input,
            graph=graph
        )
        
        return response
            
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {str(e)}"
        )
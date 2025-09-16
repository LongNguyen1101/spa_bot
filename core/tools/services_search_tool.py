import json
from shutil import ExecError
from pydantic import BaseModel, Field
from typing import Annotated, Optional, List

from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from core.utils.function import build_update
from repository.sync_repo import ServiceRepo
from core.graph.state import AgentState, Services
from database.connection import supabase_client, embeddings_model

from log.logger_config import setup_logging

logger = setup_logging(__name__)

service_repo = ServiceRepo(supabase_client=supabase_client)

def _update_seen_services(
    seen_services: dict, 
    services: List[dict]
) -> dict:
    """
    Updates `seen_services` in the state with the returned service results.

    Args:
        seen_services (dict): The existing set of seen services.
        services (List[dict]): The list of services from SQL/RAG.

    Returns:
        dict: The `seen_services` set after being updated/overwritten by `service_id`.
    """
    for service in services:
        service_id = service.get("id")
        
        seen_services[service_id] = Services(
            service_id=service_id,
            service_type=service["type"],
            service_name=service["name"],
            duration_minutes=service["duration_minutes"],
            price=service["price"]
        )
    return seen_services

@tool
def get_services_tool(
    keyword: Annotated[str, "Only accept Vietnamese - The keyword provided by the customer that refers to a specific service"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool when the customer is asking about a **specific service**.

    - If the customer provides the exact full service name, the tool will perform an exact SQL search.  
    - If the customer only provides partial information (e.g., general description), the tool will use semantic search (RAG) to find the closest matching services.

    Purpose: Retrieve detailed information about one or more spa services, such as description, duration, and price.  

    Parameters:
        - keyword (str): Only accept Vietnamese - The essential keyword (name, or core description) of the service the customer is asking about.
    """
    
    logger.info(f"get_services_tool called with keyword: {keyword}")
    # --- SQL First Approach ---
    try:
        db_result = service_repo.get_service_by_keyword(
            keyword=keyword
        )
     
        # logger.info(f"SQL data returned: {db_result}")

        if db_result:
            logger.info("Data returned from SQL")
            
            updated_seen_services = _update_seen_services(
                seen_services=state["seen_services"] if state["seen_services"] is not None else {},
                services=db_result
            )
            
            formatted_response = (
                "Here are the services found based on the customer's request:\n"
                f"{db_result}\n"
            )
            
            logger.info("Returning results from SQL")
            return Command(
                update=build_update(
                    content=formatted_response,
                    tool_call_id=tool_call_id,
                    seen_services=updated_seen_services
                )
            )
            
        logger.info("No results from SQL, switching to RAG search")
        
        query_embedding = embeddings_model.embed_query(state["user_input"])
        
        rag_results = service_repo.get_services_by_embedding(
            query_embedding=query_embedding,
            match_count=5
        )
        
        # logger.info(f"RAG results: {rag_results}")
        
        if not rag_results:
            logger.info("No results from RAG")
            return Command(update=build_update(
                content="Apologies, we couldn't find the service you're looking for.",
                tool_call_id=tool_call_id
            ))

        logger.info("Results returned from RAG")
        services = [item.get("content") for item in rag_results]
        
        if not services:
            logger.info("Could not parse service from RAG json result")
            return Command(update=build_update(
                content="Apologies, there was an error during the service search process.",
                tool_call_id=tool_call_id
            ))

        updated_seen_services = _update_seen_services(
            seen_services=state["seen_services"] if state["seen_services"] is not None else {},
            services=services
        )
        
        formatted_response = (
            "Here are the services returned based on the customer's request:\n\n"
            f"{services}\n"
        )
        
        logger.info("Returning results from RAG")
        return Command(
            update=build_update(
                content=formatted_response,
                tool_call_id=tool_call_id,
                seen_services=updated_seen_services
            )
        )

    except Exception as e:
        logger.error(f"Error: {e}")
        raise

# @tool
# def get_spa_info_tool(
#     tool_call_id: Annotated[str, InjectedToolCallId]
# ) -> Command:
#     """
#     Use this tool when the customer is asking about **general information** about the spa.  
#     DO NOT use this tool for specific service details.

#     Examples of usage:
#       - Customer asks about opening/closing hours.
#       - Customer asks about available categories of services.
#       - Customer wants general store information.

#     Purpose: Retrieve high-level information about SPA AnVie (store info, service categories, working hours, etc.).
#     """
#     logger.info(f"get_spa_info_tool called")
    
#     try:
#         with open("core/prompts/spa_info.md", "r", encoding="utf-8") as f:
#             spa_info = f.read()
        
#         return Command(
#             update=build_update(
#                 content=(
#                     "Here is the spa's information:\n"
#                     f"{spa_info}"
#                 ),
#                 tool_call_id=tool_call_id
#             )
#         )
#     except Exception as e:
#         logger.error(f"Error: {e}")
#         raise




# @tool
# def get_qna_tool(
#     state: Annotated[AgentState, InjectedState],
#     tool_call_id: Annotated[str, InjectedToolCallId]
# ) -> Command:
#     """
#     Use this tool for questions about user manuals, troubleshooting, device setup, or other technical issues.
#     The tool will search the Question & Answer (Q&A) database to provide detailed answers and instructions.

#     Function: Answer technical-related questions.
#     """
#     query = state["user_input"]
#     logger.info(f"get_qna_tool called with query: {query}")
#     all_documents = []
    
#     # --- 1. Retrieve documents from qna table ---
#     try:
#         query_embedding = embeddings_model.embed_query(query)
        
#         response = product_repo.get_qna_by_embedding(
#             query_embedding=query_embedding,
#             match_count=3
#         )

#         if not response:
#             logger.error("Error calling RPC match_qna")
#             return Command(
#                 update=build_update(
#                     content="Sorry, an error occurred while searching for instructions.",
#                     tool_call_id=tool_call_id
#                 )
#             ) 
              
#         for item in response:
#             all_documents.append(item.get("content", ""))
        
#         logger.info(f"Found {len(all_documents)} Q&A documents")
#         return Command(
#             update=build_update(
#                 content=f"Here is the information found related to the customer's question:({all_documents})",
#                 tool_call_id=tool_call_id
#             )
#         )
             
#     except Exception as e:
#         logger.error(f"Error: {e}")
#         raise

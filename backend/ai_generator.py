import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to two tools for course information.

Tool Usage:
- `search_course_content` — semantic search over course material. Use it for questions about specific content, explanations, or details taught inside a course.
- `get_course_outline` — returns a course's title, link, and complete lesson list. Use it for questions about a course's structure: what lessons it has, what it covers overall, or how it is organized.
- Use these tools **only** for questions about courses; both accept partial course titles.
- **One round of tool use per query maximum** — you may call both tools in that single round, but you will not get another turn to call tools afterwards.
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without using tools
- **Course-specific questions**: Use the appropriate tool first, then answer
- **Outline questions**: List every lesson the tool returned, with its number and title — do not summarize or truncate the list
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, tool explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    @staticmethod
    def _text_from(response) -> str:
        """Pull the answer out of a response's content blocks.

        content is heterogeneous - a thinking block, or the tool_use block
        itself, can precede the text - so block 0 is not necessarily the answer.
        """
        text = next(
            (block.text for block in response.content
             if getattr(block, "type", None) == "text"),
            "",
        )
        if response.stop_reason == "max_tokens":
            # Otherwise a cut-off answer is indistinguishable from a complete one
            return f"{text}\n\n[Response truncated: the answer hit the length limit.]"
        return text

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            
        Returns:
            Generated response as string
        """
        
        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }
        
        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        
        # Get response from Claude
        response = self.client.messages.create(**api_params)
        
        # Handle tool execution if needed. A "tool_use" stop_reason with no
        # tool_use block, or with no manager to run it, has nothing to send
        # back - a second call would end on an assistant turn and be rejected.
        has_tool_calls = any(
            getattr(block, "type", None) == "tool_use" for block in response.content
        )
        if response.stop_reason == "tool_use" and has_tool_calls:
            if tool_manager is None:
                return (
                    "This question needs a course-material lookup, but no tools "
                    "are available to answer it."
                )
            return self._handle_tool_execution(response, api_params, tool_manager)

        # Return direct response
        return self._text_from(response)
    
    def _handle_tool_execution(self, initial_response, base_params: Dict[str, Any], tool_manager):
        """
        Handle execution of tool calls and get follow-up response.
        
        Args:
            initial_response: The response containing tool use requests
            base_params: Base API parameters
            tool_manager: Manager to execute tools
            
        Returns:
            Final response text after tool execution
        """
        # Start with existing messages
        messages = base_params["messages"].copy()
        
        # Add AI's tool use response
        messages.append({"role": "assistant", "content": initial_response.content})
        
        # Execute all tool calls and collect results
        tool_results = []
        for content_block in initial_response.content:
            if content_block.type == "tool_use":
                tool_result = tool_manager.execute_tool(
                    content_block.name, 
                    **content_block.input
                )
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": tool_result
                })
        
        # Add tool results as single message
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        
        # Prepare final API call without tools
        final_params = {
            **self.base_params,
            "messages": messages,
            "system": base_params["system"]
        }
        
        # Get final response
        final_response = self.client.messages.create(**final_params)
        return self._text_from(final_response)
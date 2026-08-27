import sys
sys.path.insert(0, '.')
from memory.memory_manager import MemoryManager
import asyncio

async def test_memory_manager():
    # Initialize the memory manager
    mem = MemoryManager()
    await mem.initialize()
    
    # Add a conversation
    user_text = "Alex pediu para abrir o Chrome"
    assistant_text = "Abrindo o Chrome"
    result = await mem.add_conversation(user_text, assistant_text, engine="test")
    print(f"Added conversation: {result}")
    
    # Check that we can retrieve the episodic memory (via the internal episodic memory)
    from memory.episodic_memory import _default_store
    # Search for the conversation we just added
    search_results = _default_store.search("Alex pediu para abrir o Chrome", limit=1)
    print(f"Search results: {search_results}")
    if search_results:
        print(f"Found episode: {search_results[0]['content']}")
    else:
        print("Episode not found!")

# Run the test
asyncio.run(test_memory_manager())
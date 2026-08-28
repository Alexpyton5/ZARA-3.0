import time
from datetime import datetime
from shared_memory import SharedMemory
from vigilance import Vigilance
from capability_registry import get_capability_registry

def main():
    print("=== Hermes Worker Example Started ===")
    # Initialize shared memory
    mem = SharedMemory('hermes_shared.json')
    
    # Add a fact about current operation
    mem.add_fact('worker_started', f'Hermes worker example started at {datetime.now().isoformat()}')
    print(f"Added fact: worker_started")
    
    # Simulate some work: check capability registry for suggestion
    registry = get_capability_registry()
    suggestion = registry.get_routing_suggestion("improve ZARA memory system")
    print(f"Capability suggestion: {suggestion['suggested_capability']} (model: {suggestion['model_tier']})")
    
    # Update fact with work done
    mem.add_fact('last_work_done', f"Suggested capability for improvement: {suggestion['suggested_capability']}")
    print("Updated fact: last_work_done")
    
    # Set up a simple vigilance watch on the shared memory file itself
    def on_change(changes):
        print(f"[VIGILANCE] Detected changes: {changes}")
        # When shared memory changes, we could trigger another action
        mem.add_fact('vigilance_triggered', f"Vigilance triggered at {datetime.now().isoformat()}")
    
    watcher = Vigilance(
        watch_paths=['hermes_shared.json'],
        callback=on_change,
        poll_interval=2
    )
    
    print("Starting vigilance watch (will check for changes every 2 seconds)...")
    print("Worker will run for 10 seconds then exit.")
    
    # Run for a short time to demonstrate
    start = time.time()
    while time.time() - start < 10:
        watcher.check_changes()
        time.sleep(1)
    
    # Final summary
    all_facts = mem._load_data()
    print("\n=== Final Shared Memory State ===")
    for fid, fact in all_facts.items():
        print(f"{fid}: {fact['content'][:50]}{'...' if len(fact['content']) > 50 else ''}")
    
    print("\n=== Worker Example Completed ===")

if __name__ == "__main__":
    main()
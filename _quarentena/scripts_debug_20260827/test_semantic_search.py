#!/usr/bin/env python3
"""Test semantic search functionality in BrainStore."""

import sys
import os
sys.path.insert(0, '.')

from brain.store import BrainStore, Compartment
import tempfile
import shutil
from pathlib import Path

def test_semantic_search():
    # Create a temporary directory for testing
    test_dir = Path(tempfile.mkdtemp())
    try:
        # Initialize BrainStore with test directory
        store = BrainStore(root=test_dir)
        store.initialize()
        
        # Add some test notes to different compartments
        test_notes = [
            ("memory", "Alex gosta de café preto pela manhã", "memory_test_1.md"),
            ("memory", "Alex trabalha como desenvolvedor de software", "memory_test_2.md"),
            ("knowledge", "Inteligência artificial está transformando diversas indústrias", "knowledge_test_1.md"),
            ("knowledge", "Machine learning permite que computadores aprendam com dados", "knowledge_test_2.md"),
            ("skill", "Como preparar um bom café expresso em casa", "skill_test_1.md"),
            ("skill", "Passo a passo para configurar ambiente de desenvolvimento Python", "skill_test_2.md"),
        ]
        
        for compartment_str, content, filename in test_notes:
            compartment = Compartment(compartment_str)
            note_path = store.root / "vault" / compartment.value / "notes" / filename
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(content, encoding="utf-8")
            
            # Manually add to store (simulating import)
            store._upsert_document(
                compartment=compartment,
                digest="test_digest_" + filename,
                title=filename.replace("_test_", " ").replace(".md", "").title(),
                content=content,
                note_path=str(note_path.relative_to(store.root / "vault" / compartment.value / "notes")),
                source_label="test",
                source_root=str(test_dir),
                source_path=filename
            )
        
        print("Added test notes to all compartments")
        
        # Test semantic search across all compartments
        print("\n=== Testing cross-compartment semantic search ===")
        results = store.search_semantic("Alex gosta de bebida quente", limit=3)
        print(f"Search for 'Alex gosta de bebida quente': Found {len(results)} results")
        for i, citation in enumerate(results):
            print(f"  {i+1}. [{citation.compartment}] {citation.title}: {citation.excerpt[:50]}...")
        
        # Test semantic search in specific compartment
        print("\n=== Testing MEMORY compartment semantic search ===")
        results = store.search_semantic_compartment(Compartment.MEMORY, "desenvolvedor software", limit=2)
        print(f"Search for 'desenvolvedor software' in MEMORY: Found {len(results)} results")
        for i, citation in enumerate(results):
            print(f"  {i+1}. [{citation.compartment}] {citation.title}: {citation.excerpt[:50]}...")
        
        print("\n=== Testing KNOWLEDGE compartment semantic search ===")
        results = store.search_semantic_compartment(Compartment.KNOWLEDGE, "inteligencia artificial aprendizado", limit=2)
        print(f"Search for 'inteligencia artificial aprendizado' in KNOWLEDGE: Found {len(results)} results")
        for i, citation in enumerate(results):
            print(f"  {i+1}. [{citation.compartment}] {citation.title}: {citation.excerpt[:50]}...")
        
        print("\n=== Testing SKILL compartment semantic search ===")
        results = store.search_semantic_compartment(Compartment.SKILL, "como fazer cafe", limit=2)
        print(f"Search for 'como fazer cafe' in SKILL: Found {len(results)} results")
        for i, citation in enumerate(results):
            print(f"  {i+1}. [{citation.compartment}] {citation.title}: {citation.excerpt[:50]}...")
        
        # Test that regular search still works
        print("\n=== Testing regular lexical search still works ===")
        results = store.search("cafe preto", limit=3)
        print(f"Lexical search for 'cafe preto': Found {len(results)} results")
        for i, citation in enumerate(results):
            print(f"  {i+1}. [{citation.compartment}] {citation.title}: {citation.excerpt[:50]}...")
            
        print("\n✅ All tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    success = test_semantic_search()
    sys.exit(0 if success else 1)
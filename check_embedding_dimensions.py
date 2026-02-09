#!/usr/bin/env python3
"""
Check dimensions of all FAISS embedding indices.
"""
import faiss
from pathlib import Path

EMB_DIR = Path("embeddings")

def check_dimensions():
    """Check dimensions of all embedding files."""
    print("Checking embedding file dimensions...\n")
    
    embedding_files = list(EMB_DIR.glob("*.index"))
    
    if not embedding_files:
        print(f"No embedding files found in {EMB_DIR}")
        return
    
    dimension_groups = {}
    
    for emb_file in sorted(embedding_files):
        try:
            idx = faiss.read_index(str(emb_file))
            dim = idx.d
            ntotal = idx.ntotal
            
            if dim not in dimension_groups:
                dimension_groups[dim] = []
            dimension_groups[dim].append((emb_file.name, ntotal))
            
            print(f"✓ {emb_file.name}: {dim} dimensions, {ntotal} vectors")
            
        except Exception as e:
            print(f"✗ {emb_file.name}: ERROR - {e}")
    
    print("\n" + "="*60)
    print("SUMMARY:")
    print("="*60)
    
    for dim, files in sorted(dimension_groups.items()):
        print(f"\n{dim} dimensions ({len(files)} files):")
        for filename, ntotal in files:
            print(f"  - {filename} ({ntotal} vectors)")
    
    if len(dimension_groups) > 1:
        print("\n⚠️  WARNING: Multiple dimension sizes found!")
        print("All embeddings should use the same dimension (1536 for text-embedding-3-small)")
        print("You may need to regenerate some embeddings.")
    elif len(dimension_groups) == 1:
        dim = list(dimension_groups.keys())[0]
        if dim == 1536:
            print("\n✓ All embeddings use the correct dimension (1536)")
        else:
            print(f"\n⚠️  All embeddings use dimension {dim}, but expected 1536")
            print("You should regenerate embeddings with text-embedding-3-small")

if __name__ == "__main__":
    check_dimensions()

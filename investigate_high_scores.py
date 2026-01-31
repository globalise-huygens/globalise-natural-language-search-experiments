#!/usr/bin/env python3
"""
Investigate why normalized embeddings have such high similarity scores.
"""

import faiss
import numpy as np
from openai import OpenAI
import sqlite3
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()
query = 'consequences of volcanic eruptions'

print("="*80)
print("INVESTIGATING HIGH SIMILARITY SCORES IN NORMALIZED EMBEDDINGS")
print("="*80)

# Get query embedding
response = client.embeddings.create(
    input=[query],
    model='text-embedding-3-small'
)
query_vec = np.array([response.data[0].embedding], dtype=np.float32)
faiss.normalize_L2(query_vec)

# Test against normalized index
print("\n1. Testing normalized embeddings (1120):")
index_norm = faiss.read_index('embeddings/1120_translated_normalized.index')
distances_norm, indices_norm = index_norm.search(query_vec, 10)
print(f"   Top 10 scores: {[f'{d:.4f}' for d in distances_norm[0]]}")
print(f"   Average: {distances_norm[0].mean():.4f}")
print(f"   Min: {distances_norm[0].min():.4f}, Max: {distances_norm[0].max():.4f}")

# Test against regular translated index  
print("\n2. Testing regular translated embeddings (1120):")
index_trans = faiss.read_index('embeddings/1120_translated.index')
distances_trans, indices_trans = index_trans.search(query_vec, 10)
print(f"   Top 10 scores: {[f'{d:.4f}' for d in distances_trans[0]]}")
print(f"   Average: {distances_trans[0].mean():.4f}")
print(f"   Min: {distances_trans[0].min():.4f}, Max: {distances_trans[0].max():.4f}")

# Check what text was actually embedded
print("\n3. Checking what text is in the database vs embeddings:")
conn = sqlite3.connect('text-metadata-sqlite/voc_documents.db')
cursor = conn.cursor()

# Get the text for the top result from normalized
cursor.execute('''
SELECT text_translated_normalized, text_translated_clean, LENGTH(text_translated_normalized), LENGTH(text_translated_clean)
FROM documents 
WHERE inv_nr='1120'
ORDER BY chunk_id
LIMIT 1
OFFSET ?
''', (int(indices_norm[0][0]),))

norm_text, clean_text, norm_len, clean_len = cursor.fetchone()
print(f"\n   Top result from normalized (chunk {indices_norm[0][0]}):")
print(f"   Normalized text length: {norm_len}")
print(f"   Clean text length: {clean_len}")
print(f"   First 200 chars of normalized: {norm_text[:200]}")

# Now generate embedding from this exact text and see if it matches
print("\n4. Verifying embedding consistency:")
response_norm = client.embeddings.create(
    input=[norm_text],
    model='text-embedding-3-small'
)
test_vec_norm = np.array([response_norm.data[0].embedding], dtype=np.float32)
faiss.normalize_L2(test_vec_norm)

# Get the stored vector from index
stored_vec = np.zeros(index_norm.d, dtype=np.float32)
index_norm.reconstruct(int(indices_norm[0][0]), stored_vec)

# Compare
similarity = np.dot(test_vec_norm[0], stored_vec)
print(f"   Re-embedded same text, similarity to stored vector: {similarity:.6f}")
if similarity < 0.99:
    print("   ⚠️  WARNING: Stored embedding doesn't match re-embedding of same text!")
    print("   This suggests the embeddings were generated from different text.")
else:
    print("   ✅ Stored embedding matches (embeddings were created correctly)")

# Check variance in the corpus
print("\n5. Checking corpus variance:")
sample_size = min(100, index_norm.ntotal)
vectors_norm = np.zeros((sample_size, index_norm.d), dtype=np.float32)
vectors_trans = np.zeros((sample_size, index_trans.d), dtype=np.float32)

for i in range(sample_size):
    index_norm.reconstruct(i, vectors_norm[i])
    index_trans.reconstruct(i, vectors_trans[i])

# Calculate pairwise similarities
similarities_norm = np.dot(vectors_norm, vectors_norm.T)
similarities_trans = np.dot(vectors_trans, vectors_trans.T)

# Get upper triangle (excluding diagonal)
mask = np.triu(np.ones_like(similarities_norm, dtype=bool), k=1)

print(f"   Pairwise similarities (normalized embeddings):")
print(f"     Mean: {similarities_norm[mask].mean():.4f}")
print(f"     Std: {similarities_norm[mask].std():.4f}")
print(f"     Min: {similarities_norm[mask].min():.4f}")
print(f"     Max: {similarities_norm[mask].max():.4f}")

print(f"\n   Pairwise similarities (regular translated embeddings):")
print(f"     Mean: {similarities_trans[mask].mean():.4f}")
print(f"     Std: {similarities_trans[mask].std():.4f}")
print(f"     Min: {similarities_trans[mask].min():.4f}")
print(f"     Max: {similarities_trans[mask].max():.4f}")

if similarities_norm[mask].mean() > similarities_trans[mask].mean() + 0.05:
    print("\n   ⚠️  Normalized corpus has significantly higher inter-document similarity!")
    print("   This means normalized texts are more similar to each other.")
else:
    print("\n   ✅ Corpus similarity is comparable")

conn.close()

print("\n" + "="*80)

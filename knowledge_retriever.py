import os
import re
import math

def get_tokens(text):
    tokens = []
    current_word = []
    for char in text.lower():
        if '\u4e00' <= char <= '\u9fff':
            if current_word:
                tokens.append("".join(current_word))
                current_word = []
            tokens.append(char)
        elif char.isalnum():
            current_word.append(char)
        else:
            if current_word:
                tokens.append("".join(current_word))
                current_word = []
    if current_word:
        tokens.append("".join(current_word))
    return tokens

def compute_cosine_similarity(q_tokens, doc_tokens):
    if not q_tokens or not doc_tokens:
        return 0.0
    
    # Calculate word frequencies
    q_freq = {}
    for t in q_tokens:
        q_freq[t] = q_freq.get(t, 0) + 1
        
    doc_freq = {}
    for t in doc_tokens:
        doc_freq[t] = doc_freq.get(t, 0) + 1
        
    # Unique tokens union
    all_tokens = set(q_freq.keys()).union(set(doc_freq.keys()))
    
    # Dot product and magnitudes
    dot_product = 0.0
    q_mag = 0.0
    doc_mag = 0.0
    for t in all_tokens:
        q_val = q_freq.get(t, 0.0)
        doc_val = doc_freq.get(t, 0.0)
        dot_product += q_val * doc_val
        q_mag += q_val * q_val
        doc_mag += doc_val * doc_val
        
    if q_mag == 0 or doc_mag == 0:
        return 0.0
    return dot_product / (math.sqrt(q_mag) * math.sqrt(doc_mag))

def retrieve_knowledge(query, knowledge_dir=None, top_n=3):
    if knowledge_dir is None:
        knowledge_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge")
        
    if not os.path.exists(knowledge_dir):
        return []
        
    chunks = []
    # Read files in knowledge_dir
    for filename in os.listdir(knowledge_dir):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(knowledge_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                # Split by double newline to get paragraphs
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                for idx, para in enumerate(paragraphs):
                    chunks.append({
                        "source": filename,
                        "paragraph_idx": idx,
                        "text": para,
                        "tokens": get_tokens(para)
                    })
        except Exception:
            continue
            
    if not chunks:
        return []
        
    q_tokens = get_tokens(query)
    if not q_tokens:
        return []
    
    # Calculate similarity score for each chunk
    scored_chunks = []
    for chunk in chunks:
        score = compute_cosine_similarity(q_tokens, chunk["tokens"])
        
        # Simple substring matching boost
        overlap_count = sum(1 for q_t in q_tokens if q_t in chunk["tokens"])
        if overlap_count > 0:
            score += 0.1 * overlap_count
            
        scored_chunks.append((chunk, score))
        
    # Sort by score descending
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # Return top_n chunks
    return [item[0] for item in scored_chunks[:top_n] if item[1] > 0.02]

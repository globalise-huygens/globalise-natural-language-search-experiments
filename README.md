# Natural Language Search for VOC Documents

## What does this notebook do?

This notebook enables you to search historical VOC documents using **natural language questions** (in Dutch or another language). Instead of needing exact search terms, you can ask questions like *"what was life like for enslaved people"* and get the most relevant text fragments in return.

## Setup

### Prerequisites
Before running the notebook, you need to:

1. **Create a `.env` file** in the same directory as the notebook with your OpenAI API key:
   ```
   OPENAI_API_KEY=your-api-key-here
   ```

2. **Run Cell 1** to load the API key from the environment file and load/install all dependencies.
   
## Step-by-step explanation

### 1. **Load documents** (Cell 2)
- The notebook reads all CSV files from the `text-input` folder
- Each file contains transcribed text from pages of one inventory number
- All texts are combined into one large table

### 2. **Clean text** (Cell 3)
- Strange characters are replaced (like â€ž → ")
- Extra whitespace is removed
- This ensures more consistent search results

### 3. **Split text into 'chunks'** (Cell 4)
- Each document is divided into pieces of **500 words**
- These pieces overlap by **100 words**
- Why? Because the search technology works better with smaller, manageable text fragments
- **Important**: Chunks continue across page boundaries so you don't lose context

### 4. **Store in database** (Cell 6)
- All chunks are saved in a SQLite database (`voc_documents.db`)
- For each chunk, we track:
  - Which inventory number it belongs to
  - Which page(s) the text appears on
  - The full text of the fragment

### 5. **Create embeddings** (Cell 7)
- This is the 'smart' part: each chunk is converted into a numerical representation (an 'embedding')
- These embeddings capture the **meaning** of the text
- They are stored in a FAISS index (a type of efficient search index)
- This happens automatically the first time you search in an inventory number
- After that, the embeddings are reused (much faster!)

### 6. **Search** (Cell 8-9)
When you submit a search query:

1. **Your question becomes an embedding**: The search query gets the same numerical representation
2. **Compare**: The system finds which chunks are most similar to your question (semantically similar, not literal matches)
3. **Sort results**: The most relevant fragments appear at the top
4. **Add explanations**: For the top 5 results, the system generates a brief explanation of why this fragment is relevant
5. **Save**: Results are saved as CSV in the `results` folder

## What do you get back?

A table with:
- **inv_nr**: The inventory number
- **start_page**: The first page of the fragment
- **pages**: All pages included in this fragment
- **similarity**: How relevant the fragment is (higher = more relevant)
- **verantwoording**: Why this fragment is relevant to your question
- **text**: The complete text of the fragment

## How to use it?

In the last cell, modify:

```python
query_text = "your question here"
df_results = search_query(query_text, inv_nrs=["1120", "1267"], verantwoording_top=5)
```

- **query_text**: Your search question in plain language
- **inv_nrs**: List of inventory numbers you want to search in (make sure the text of these inventory numbers is included in csv file format in the text-input folder).
- **verantwoording_top**: How many results you want explanations for (default 5)

## Important notes

- **First time is slow**: The first time you search in an inventory number, it takes longer because embeddings are being created. After that, it's much faster!
- **API costs**: The system uses OpenAI's API, which costs money per search query (a few cents per question)
- **Results in CSV**: Always check the `results` folder for detailed results

## Tips for good search results

**Do:**
- Ask concrete questions: "How was coffee transported?"
- Use thematic search queries: "life aboard VOC ships"
- Search for concepts: "trade conflicts with the English"

**Don't:**
- Search for exact quotes (use Ctrl+F for that)
- Ask overly broad questions: "tell me about the VOC"
- Expect modern terminology in historical texts

## Chunk sizes explained

The notebook uses **word-based chunking**:
- `CHUNK_SIZE = 500` means 500 words per chunk
- `CHUNK_OVERLAP = 100` means 100 words overlap between consecutive chunks

These are **words** (whitespace-delimited), not tokens or characters:
- 5000 words ≈ ~666 tokens ≈ ~3,500 characters

This stays well within OpenAI's embedding model limit of 8,191 tokens.

from langchain_ollama import OllamaEmbeddings,OllamaLLM
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

# prompt 
RAG_SEARCH_PROMPT_TEMPLATE="""
    Using the following pieces of retrieved context, answer the question comprehensively and concisely.
Ensure your response fully addresses the question based on the given context.

**IMPORTANT:**
Just provide the answer and never mention or refer to having access to the external context or information in your answer.
If you are unable to determine the answer from the provided context, state 'I don't know.'

Question: {question}
Context: {context}
"""

print("Loading and chunking Docs")
loader = TextLoader("./data/agency.txt")
docs = loader.load()

doc_splitter = RecursiveCharacterTextSplitter(chunk_size=800,chunk_overlap=150)
docs_chunk = doc_splitter.split_documents(docs)

print("Creating New Vector Embeddings")

embeddings = OllamaEmbeddings(model="nomic-embed-text")

vectorstore = Chroma.from_documents(docs_chunk,embeddings,persist_directory="db")
vectorstore_retreiver = vectorstore.as_retriever(search_kwargs={"k":5})
print("Vector Store Retriver Created")

print("Test Rag Chain")
prompt = ChatPromptTemplate.from_template(RAG_SEARCH_PROMPT_TEMPLATE)

llm = OllamaLLM(model='llama3:latest')

Rag_chain = (
    {"context":vectorstore_retreiver , "question":RunnablePassthrough()}
    |prompt
    |llm
    |StrOutputParser()
)

query = "What are the pricing options"
result = Rag_chain.invoke(query)

print(result)





# here we will create various runnables which we will provide to the agents later on to perform different task
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from .prompts import *
from .structure_out import *
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser


class Agents:
    def __init__(self):
        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        llm = ChatOllama(model="llama3:latest", temperature=0)
        vectorstore = Chroma(persist_directory="db", embedding_function=embeddings)
        retreiver = vectorstore.as_retriever(search_kwargs={"k": 5})

        email_category_prompt = PromptTemplate(
            template=CATEGORIZE_EMAIL_PROMPT,
            input_variables=["email"]
        )
        self.categorize_email = (
            email_category_prompt
            | llm.with_structured_output(CategorizeEmailOutput, method="json_schema")
        )


        generate_query_prompt = PromptTemplate(
            template=GENERATE_RAG_QUERIES_PROMPT,
            input_variables=["email"]
        )
        self.design_rag_queries = (
            generate_query_prompt
            | llm.with_structured_output(RAGQueriesOutput, method="json_schema")
        )


        qa_prompt = ChatPromptTemplate.from_template(GENERATE_RAG_ANSWER_PROMPT)
        self.generate_rag_answer = (
            {"context": retreiver, "question": RunnablePassthrough()}
            | qa_prompt
            | llm
            | StrOutputParser()
        )


        writer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EMAIL_WRITER_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "{email_information}")
            ]
        )
        self.email_writer = (
            writer_prompt
            | llm.with_structured_output(WriterOutput, method="json_schema")
        )


        proofreader_prompt = PromptTemplate(
            template=EMAIL_PROOFREADER_PROMPT,
            input_variables=["initial_email", "generated_email"]
        )
        self.email_proofreader = (
            proofreader_prompt
            | llm.with_structured_output(ProofReaderOutput, method="json_schema")
        )


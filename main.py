import os
from colorama import Fore, Style
from src.graph import Workflow
from dotenv import load_dotenv

# Load all env variables
load_dotenv()

# config 
config = {'recursion_limit': 100}

def main():
    workflow = Workflow()
    print(os.getenv("GOOGLE_API_KEY"))
    initial_state = {
            "emails": [],
            "current_email": {
            "id": "",
            "threadId": "",
            "messageId": "",
            "references": "",
            "sender": "",
            "subject": "",
            "body": "",
        },
        "email_category": "",
        "generated_email": "",
        "rag_queries": [],
        "retrieved_documents": "",
        "writer_messages": [],
        "sendable": False,
        "trials": 0,
    } 

    #stream the events of graph for debugging
    for event in workflow.app.stream(
        initial_state,
        config=config
    ):
      print(event)

    # result = workflow.app.invoke(initial_state)
    # print(result)

if __name__ == "__main__":
    main()



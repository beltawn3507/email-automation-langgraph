from colorama import Fore, Style
from src.graph import Workflow
from src.live_runner import build_initial_state
from dotenv import load_dotenv

# Load all env variables
load_dotenv()

# config 
config = {'recursion_limit': 100}

workflow = Workflow()
app = workflow.app

initial_state = build_initial_state()

# Run the automation
print(Fore.GREEN + "Starting workflow..." + Style.RESET_ALL)
for output in app.stream(initial_state, config):
    for key, value in output.items():
        print(Fore.CYAN + f"Finished running: {key}:" + Style.RESET_ALL)


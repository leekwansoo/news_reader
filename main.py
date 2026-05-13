# main program for CrewAI news reader agent, which will use the collector_agent
# to gather information and updates based on the specified description and expected output.

# import dependencies

# Environment
from dotenv import load_dotenv
import os
load_dotenv()
os.environ["GOOGLE_API_KEY"]=os.getenv("GOOGLE_API_KEY")
os.environ["OPENAI_API_KEY"]=os.getenv("OPENAI_API_KEY")
import google.genai as genai
from crewai import LLM, Task, Agent

# Use a CrewAI-compatible LLM wrapper for local Ollama models
from crewai import LLM

AGENT_LLM = LLM(
    model="openai/gpt-4o",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.2,
)


from crewai.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun


search_tool_instance = DuckDuckGoSearchRun()

@tool("DuckDuckGo Search")
def search_tool(query: str) -> str:
    """A tool for searching the web using DuckDuckGo."""
    return search_tool_instance.run(query)

# Define Agents

# Defining Agents

from crewai import Agent


collector_agent = Agent(
    role="Content Collector",
    goal="Gather the latest updates and articles specifically about IT, AI advancements, AI agents, and the tech market from trusted public sources for daily review.",
    backstory="""
    You are a highly focused content collector who specializes in tracking the most relevant updates in technology and AI.
    Your task is to find daily news, insights, and breakthroughs that matter to professionals and enthusiasts,
    ignoring unrelated or low-value content. You prioritize relevance, timeliness, and authority of sources.""",
    verbose=False,
    llm=AGENT_LLM,
    tools=[search_tool],
    max_iter=2,
 )

# Creating Tasks

from crewai import Task
# this task is assigned to the collector_agent, which will use the search_tool to gather information and updates based on the specified description and expected output.

collector_task = Task(
    description="""
    Collect the latest public updates and articles related to:
    1. IT industry developments
    2. AI advancements and research
    3. AI agents and frameworks
    4. Tech market news and trends

    Focus on content from the past 24–48 hours. Gather information that is relevant, high-quality,
    and actionable for professionals who want to stay informed daily.
    """,
    expected_output="A curated list of recent articles, news items, and updates in IT, AI, AI agents, and the tech market, with key points summarized for each item.",
    agent=collector_agent
)

# Executing the Crew

from crewai import Crew, Process

collector_crew = Crew(
    agents= [collector_agent],
    tasks=[collector_task],
    process=Process.sequential,
    verbose=True
)

print("@ Launching Collector Crew...")
research_result = collector_crew.kickoff()
from IPython.display import Markdown

print("Collector REPORT COMPLETE")
Markdown (research_result.raw)
import sys
from openai import OpenAI

# Initialize the OpenAI-compatible routing client
client = OpenAI(
    # Explicitly targeted to process direct completions on Modal's server
    base_url="https://modal.com", 
    api_key="wk-ez3b0wleG5MVTXnCbpH0qy.ws-hHMMtq8YeaM6EVUur0pPAvS"
)

# Initialize standard conversational memory
conversation_history = [
    {
        "role": "system", 
        "content": "You are Kimi K3, a helpful and hyper-intelligent AI assistant running on Modal serverless infrastructure."
    }
]

print("====================================================")
print("?? Kimi K3 Pure Interactive Terminal Active")
print("   (Type your prompt directly or 'exit' to quit)")
print("====================================================\n")

while True:
    try:
        # Accept your direct keyboard prompt
        user_input = input("User > ").strip()
        
        if user_input.lower() in ['exit', 'quit']:
            print("\nGoodbye!")
            break
            
        if not user_input:
            continue
            
        conversation_history.append({"role": "user", "content": user_input})
        print("\nKimi > ", end="", flush=True)
        
        # Send the chat logs directly to the K3 engine
        response = client.chat.completions.create(
            model="kimi-k3", 
            messages=conversation_history,
            temperature=0.5,
            stream=True 
        )
        
        # Stream the characters cleanly as they are thought up
        full_response = ""
        for chunk in response:
            if chunk.choices and chunk.choices.delta and chunk.choices.delta.content:
                text_chunk = chunk.choices.delta.content
                print(text_chunk, end="", flush=True)
                full_response += text_chunk
        
        print("\n") # Line break after text completes
        conversation_history.append({"role": "assistant", "content": full_response})

    except KeyboardInterrupt:
        print("\n\nChat interrupted. Exiting...")
        break
    except Exception as e:
        print(f"\n? Connection Error: {e}\n")
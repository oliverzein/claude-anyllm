import os
from openai import OpenAI


def main():
    client = OpenAI(
        api_key=os.getenv("ATLASCLOUD_API_KEY"),
        base_url="https://api.atlascloud.ai/v1",
    )

    response = client.chat.completions.create(
        model="qwen/qwen3.6-plus",
        messages=[
            {
                "role": "user",
                "content": "hello",
            }
        ],
        max_tokens=1024,
        temperature=0.7,
    )

    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()

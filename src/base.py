# Please install OpenAI SDK first: `pip3 install openai`

from openai import OpenAI

client = OpenAI(api_key="key", base_url="https://api.deepseek.com")

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Buatkan kode html untuk mrnampilkan teks paragraf"},
    ],
    stream=False,
    temperature=0.0
)

print(response.choices[0].message.content)
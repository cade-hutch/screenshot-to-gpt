from openai import OpenAI
from PIL import Image
import pytesseract

import base64
import os
import sys
import json
import time
import requests
import re

IGNORE = [".DS_Store"]
SCREENSHOT_DIRECTORY = os.path.join(os.path.expanduser("~"), "Desktop")
API_KEY_FILE = "./keys.json"

MARKDOWN_DIR = "./markdowns"
RAW_MARKDOWN_DIR = "./markdowns_raw"
MD = ".md" # markdown extension


if not os.path.exists(MARKDOWN_DIR):
    os.mkdir(MARKDOWN_DIR)
if not os.path.exists(RAW_MARKDOWN_DIR):
    os.mkdir(RAW_MARKDOWN_DIR)

MODELS = [
    "gpt-4o",
    "o1-preview"
]

GPT_4O_SOLVE_PROMPT = "Solve the problem shown in the given image."


def get_api_key(key_file, api_name, key_name):
    try:
        with open(key_file, 'r') as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"File not found")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON file")
        return None

    key_obj = data

    api_keys = key_obj.get(api_name)

    if not api_keys:
        return None
    
    return api_keys.get(key_name)


def default_payload(image_question):
    return {
        "model" : MODELS[0],
        "messages": [
            {
            "role": "user",
            "content": [
                {
                "type": "text",
                "text": f"{image_question}"
                },
                {
                "type": "image_url",
                "image_url": {
                    "url": ""
                }
                }
            ]
            }
        ]
        #"max_tokens": 100
    }


def headers(api_key):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def send_prompt_o1(openai_api_key, prompt):
    client = OpenAI(api_key=openai_api_key)
    try:
        response = client.chat.completions.create(
            model=MODELS[1],
            messages=[{"role": "user", "content": f"{prompt}"}],
        )
        if response.choices[0].message.content:
            return response.choices[0].message.content
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def send_image_and_prompt(api_key, img_path, prompt):
      """
      Send image to vision model with prompt
      """
      #reduce_png_quality(img_path, img_path)
      base64_image = encode_image(img_path)

      start_time_req = time.perf_counter()

      payload = default_payload(prompt)
      payload['messages'][0]['content'][1]['image_url']['url'] = f"data:image/jpeg;base64,{base64_image}"

      response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers(api_key), json=payload)

      stop_time_req = time.perf_counter()
      request_time = stop_time_req - start_time_req
      print(f'response recieved for {os.path.basename(img_path)} in {request_time} seconds')

      try:
        response_description = response.json()["choices"][0]["message"]["content"]
        return response_description

      except KeyError as e:
         print(f"KeyError occurred: {e}")
         print(response.json())
         return None
      

def get_files_by_last_modified(directory, num_files=None):
    """
    Returns a list of files in the given directory, sorted by last modified time (most recent first).
    """
    files = [os.path.join(directory, f) for f in os.listdir(directory)
                if os.path.isfile(os.path.join(directory, f))]
    
    # Sort by last modified time in descending order
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    files = [f for f in files if os.path.basename(f) not in IGNORE]

    if num_files is not None:
        return files[:num_files]
    return files


def get_ss_text(img_paths) -> str:
    """
    Run tesseract on image to extract text
    """
    ss_text = ""
    for imgp in img_paths:
        text = pytesseract.image_to_string(Image.open(imgp))
        ss_text += clean_string(text)

    return ss_text


def clean_string(input_string):
    # TODO
    return input_string


def solve_with_4o(img_paths, graphic=True):
    # TODO: handle case of multiple images, graphic in one, all problems related to graphic
    if len(img_paths) > 1:
        raise NotImplementedError()
    else:
        api_key = get_api_key(API_KEY_FILE, 'open-ai', 'default')

        res = send_image_and_prompt(api_key, img_paths[0], GPT_4O_SOLVE_PROMPT)
        write_to_markdown(res)


def solve_with_o1(img_paths):
    api_key = get_api_key(API_KEY_FILE, 'open-ai', 'default')

    problem = get_ss_text(img_paths)

    res = send_prompt_o1(api_key, problem)
    if res:
        write_to_markdown(res, problem=problem)
    else:
        print('error...invalid or no response')


def write_to_markdown(answer_txt, problem=None):
    filename = "1"

    md_path = os.path.join(RAW_MARKDOWN_DIR, filename + MD)
    while os.path.exists(md_path):
        filename = str(int(filename) + 1)
        md_path = os.path.join(RAW_MARKDOWN_DIR, filename + MD)

    print(f"writing to: {md_path}")
    with open(md_path, 'w', encoding='utf-8') as f:
        if problem is not None:
            f.write("```\n")
            f.write(problem)
            f.write("\n```\n")

        f.write(answer_txt)

    output_md = os.path.join(MARKDOWN_DIR, filename + MD)
    replace_latex_delimiters(md_path, output_file=output_md)


def replace_latex_delimiters(input_file, output_file=None):
    """
    Read markdown file and replace:
    - '\[' and '\]' with '$$'
    - '\(' and '\)' with '$' (if they appear on the same line)
    """
    if output_file is None:
        output_file = input_file

    with open(input_file, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    updated_lines = []
    for line in lines:
        # Replace '\[' or '\]' with '$$'
        line = line.replace(r'\[', '$$').replace(r'\]', '$$')

        # Replace '\(' or '\)' with '$' if they both appear on the same line
        if r'\(' in line and r'\)' in line:
            line = line.replace(r'\(', '$').replace(r'\)', '$')

        updated_lines.append(line)

    with open(output_file, 'w', encoding='utf-8') as file:
        file.writelines(updated_lines)

    print(f"Formatted file at: {output_file}")


if __name__ == "__main__":
    # first arg for multiple files, defaults to 1
    num_files = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    # second arg, pass in 1 sent image to vision model instead of extracting text
    graphic_request = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    try:
        sorted_files = list(reversed(get_files_by_last_modified(SCREENSHOT_DIRECTORY, num_files)))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit()

    if graphic_request:
        print("handling graphic")
        solve_with_4o(sorted_files)
    else:
        print("handling text with o1")
        solve_with_o1(sorted_files)
    

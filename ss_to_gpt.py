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
DIR_PATH = "/Users/cadeh/Desktop"
MARKDOWN_DIR = "./markdowns"
RAW_MARKDOWN_DIR = "./markdowns_raw"


MODELS = [
    "gpt-3.5-turbo-0125",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-4-1106-preview", #*Most used
    "gpt-4o",
    #'gpt-4-turbo-2024-04-09', same as base turbo?
    "o1-preview"
]

GET_TEXT_PROMPT = "What does the text in the image say? Only reply with image text"
GPT_O1_SYSTEM_PROMPT = "" #TODO:... needed?
GPT_4O_SOLVE_PROMPT = "Solve the problem shown in the given image."
#GPT_4O_SOLVE_PROMPT = "Solve the problem shown in the given image. If the answer requires any special characters or formatting, such as a table, represent using markdown."
#NOTE:  ^ modified prompt made all answers wrong for table problem


def default_payload(image_question):
  return {
    #"model": "gpt-4-vision-preview",
    "model" : MODELS[4],
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
            model=MODELS[-1],
            messages=[{"role": "user", "content": f"{prompt}"}],
        )
        #print(response)
        if response.choices[0].message.content:
            return response.choices[0].message.content
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def send_image_and_prompt(api_key, img_path, prompt):
      #reduce_png_quality(img_path, img_path)
      base64_image = encode_image(img_path)
      start_time_req = time.perf_counter()
      payload = default_payload(prompt)
      payload['messages'][0]['content'][1]['image_url']['url'] = f"data:image/jpeg;base64,{base64_image}"
      response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers(api_key), json=payload)
      stop_time_req = time.perf_counter()
      request_time = stop_time_req - start_time_req
      print('response recieved for {} in {} seconds'.format(os.path.basename(img_path), request_time))
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
    # Get all files (excluding directories) in the directory
    files = [os.path.join(directory, f) for f in os.listdir(directory)
                if os.path.isfile(os.path.join(directory, f))]
    
    # Sort files by last modified time in descending order
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    #TODO: startswith Screenshot or endswith .png
    files = [f for f in files if os.path.basename(f) not in IGNORE]
    # Return the specified number of files, or all if num_files is None
    if num_files is not None:
        return files[:num_files]
    return files


def get_ss_text(img_paths) -> str:
    # Load the image from the uploaded file
    ss_text = ""
    for imgp in img_paths:
        text = pytesseract.image_to_string(Image.open(imgp))
        ss_text += remove_points_text(text)

    return ss_text


def remove_points_text(input_string):
    pattern = r'\([^)]*\bpoints?\b[^)]*\)'
    
    # Use re.sub to replace the matching substring with an empty string
    cleaned_string = re.sub(pattern, '', input_string)
    return cleaned_string.strip()


def solve_with_4o(img_paths, graphic=True):
    #TODO: case where multiple images, graphic in one, all problems related to graphic
    if len(img_paths) > 1:
        print('handling multiple images...')
        return
    else:
        res = send_image_and_prompt(API_KEY, img_paths[0], GPT_4O_SOLVE_PROMPT)
        #print(res)
        write_to_markdown(res)


def solve_with_o1(img_paths):
    problem = get_ss_text(img_paths)

    res = send_prompt_o1(API_KEY, problem)
    if res:
        write_to_markdown(res, problem=problem)
    else:
        print('error')


def write_to_markdown(answer_txt, problem=None):
    MD = ".md"
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
    Reads a Markdown file and replaces:
    - '\[' and '\]' with '$$'
    - '\(' and '\)' with '$' (if they appear on the same line)

    Args:
        input_file (str): Path to the input Markdown file.
        output_file (str, optional): Path to save the modified Markdown file.
                                     If None, overwrites the input file.
    """
    # Default to overwriting the input file if no output file is provided
    if output_file is None:
        output_file = input_file

    # Open the file, read lines, and replace as needed
    with open(input_file, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    # Process each line
    updated_lines = []
    for line in lines:
        # Replace '\[' and '\]' with '$$'
        line = line.replace(r'\[', '$$').replace(r'\]', '$$')

        # Replace '\(' and '\)' with '$' if they both appear on the same line
        if r'\(' in line and r'\)' in line:
            line = line.replace(r'\(', '$').replace(r'\)', '$')

        updated_lines.append(line)

    # Write the updated lines back to the file
    with open(output_file, 'w', encoding='utf-8') as file:
        file.writelines(updated_lines)

    print(f"File successfully updated: {output_file}")


if __name__ == "__main__":
    num_files = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    graphic_request = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    # replace_latex_delimiters("/Users/cadeh/Desktop/School/ecen-602/602/markdowns/1.md", output_file='./new.md')
    # sys.exit()

    try:
        sorted_files = list(reversed(get_files_by_last_modified(DIR_PATH, num_files)))
        # for file in sorted_files:
        #     print(file)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit()

    if graphic_request:
        print("handling graphic")
        solve_with_4o(sorted_files)
    else:
        print("handling with o1")
        solve_with_o1(sorted_files)
    

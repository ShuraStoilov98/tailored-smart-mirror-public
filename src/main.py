from flask import Flask, request, jsonify, send_from_directory
import json, pathlib
import os 
import base64
from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv

# Start the project
print("Smart mirror project ready 🚀")

# Initialize Flask app
app = Flask(__name__, static_folder="static", static_url_path="/static")

#######################################################
# --- Make any needed declarations of variables --- #
#######################################################

#Set up the data directories
IMAGE_INPUT_DATA_DIR   = pathlib.Path("../image_input").resolve()
TEXT_OUTPUT_DATA_DIR   = pathlib.Path("../output/text").resolve()
AUDIO_OUTPUT_DATA_DIR  = pathlib.Path("../output/audio").resolve()

# Set the file names
output_audio_file_name = AUDIO_OUTPUT_DATA_DIR / "result.mp3"
input_image_file_name =  IMAGE_INPUT_DATA_DIR / "image.png"

#Setup OpenAI client and API keys
load_dotenv(override=True)
api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI()

#Select the model for the image to text and text to text 
image_to_text_model = "gpt-image-1"
text_to_audio_model = "gpt-4o-mini-tts"
audio_voice = "alloy" # options are: alloy, ash, ballad, coral, echo, fable, onyx, nova, sage, shimmer, verse, marin, and cedar

# Define JSON output schemas
eval_schema = str("""{"number_potential_outfits":0,"number_similar_items":0,"material_quality":1,"style_match":1,\
                "lifestyle_match":1,"body_shape_fit":1, "number_of_wears":"", "reasoning_long":"", "reasoning_short":"", "overall_score":0}""")


###############################################
# --- Build the prompts for the AI calls --- #
###############################################

#Input prompt to analyse the image of outfit and produce review and score 
def build_image_to_text_outfit_prompt(output_schema):
    return f"""
TASK: From the image, analyse the main clothing item.
        Output ONLY valid JSON with this schema: {output_schema}
        RULES: 
        - all lowercase; make a guess for materials if not obvious; arrays unique/by dominance; brand only if visible, otherwise None
        - "detailed_description": one compact, factual string sufficient to reproduce the item: silhouette; length; neckline/collar; sleeve/leg; rise/waist; hem; closure; pockets; pattern/graphics; key details (pleats/stitching/cuffs); hardware; finish (matte/glossy/washed).
        - "sub_type": two words, one the main colour/adjective and one the best description of the item, e.g. black blazer, cowboy boots, black t-shirt
        - style_tag: main styles the item is in, e.g. tailored, minimalist, boho, romantic, extravagant, etc.
        - Single-select enums: type, fit.
        - Multi-select enums:  occasions, seasonality.
        - type=[top,trousers,jeans, dresses,shoes, bags, accessories, skirts, shorts, overlays]
        - fit=[relaxed,tailored,oversized,skinny]
        - occasions=[work,going out,relaxing,sports,formal events]
        - seasonality=[summer,winter,spring,autumn]

RULES:
- Use ONLY provided data; no web, no guesses. Integers only. Clamp 1-5 scales to [1,5], counts ≥0, overall_score 0-100.
- Keys exactly as in schema; no extra keys/text.

1) number_potential_outfits (count):
- An outfit = (top+bottom+shoes) OR (dress+shoes). Overlay (jacket/cardigan/coat) is optional and multiplies combos if present.
- Complement map: top-bottom, trousers-top, dresses-shoes, overlays pair with either set.
- Count combos using WARDROBE items that are (a) season-compatible (share any season or item has "all-year"), and (b) color-compatible: share a color OR either item uses a neutral (white, black, beige, navy, gray, tan, denim).
- Style harmony: avoid combos if style_tags are in direct conflict (e.g., "minimal" vs "extravagant").
- Compute products across required categories; overlays multiply if present.

2) number_similar_items (count):
- Count WARDROBE items that are same type and same sub_type and are similar to the item reviewed. 

3) material_quality (1-5):
- 5: silk, cashmere/merino wool, full-grain leather, heavy linen/denim, selvedge/goodyear-welt cues.
- 4: cotton (good weave), linen, standard denim, modal/lyocell/viscose blends with natural hand.
- 3: mixed blends or unknown quality.
- 2: polyester/chiffon/acrylic/PU or very light/delicate synthetics.
- 1: obviously flimsy/novelty construction.
(Choose the best match from BUY_ITEM.materials and description.)

4) style_match (1-5):
Start 1. +2 if any BUY_ITEM.style_tags ∩ USER.style_inspo_tags; +1 more if ≥2 tags match. +1 if brand ∈ USER.favorite_brands. +1 if any BUY_ITEM.colors ∈ USER.palette or is neutral. -1 if “extravagant” vs “minimal” clash. Clamp 1-5.

5) lifestyle_match (1-5):
Map USER.weekly_rhythm → scores by occasion:
- work: work_days 0→1, 1-2→3, 3→4, ≥4→5
- going out: evenings_out 0→1, 1→3, 2→4, ≥3→5
- sports: workouts 0→1, 1-2→3, 3→4, ≥4→5
- relaxing: casual_days 0→1, 1→3, 2→4, ≥3→5
- travel: travel_days 0→1, 1→3, 2→4, ≥3→5
- formal events: default 2 unless USER explicitly indicates frequent formals.
Take the MAX score across BUY_ITEM.occasions present.

6) body_shape_fit (1-5) using USER.appearance.body_shape and BUY_ITEM details:
- hourglass: + waist definition, wrap, V-neck, tailored; - boxy/oversized/kaftan/batwing.
- pear: + A-line/straight, structured shoulders; - clingy light bottoms.
- rectangle: + waist creation (belts/peplum/darts); - very boxy shapeless.
- apple: + V-neck, straight lines, soft midsection; - tight midriff emphasis.
Heuristic: start 3, ±1 for each strong signal. Clamp 1-5.

7) number_of_wears: 
- CAN ONLY BE AN INTEGER
- Based on lifestyle match, potential outfits and material quality compute a number of potential number of wears in the user's lifetime
- Penalise for lack of style match or body shape fit and number of similar items 

8) reasoning_long:
- Max 226 characters. One paragraph. Neutral, concise tone.
- Start: "This *primary_color* *sub_type or type* ..."
- Cover briefly: lifestyle, style fit; use-case fit; pairing breadth and duplication risk; material/durability note.
- No numbers in text, no lists, no emojis, no hedging.

9) reasoning_short:
- Max 50 characters. Summary of reasoning_long.

10) overall_score (0-100):
- potential_outfits_score = min(number_potential-_outfits,10)/10*100.
- similar_items_score = 100 min(number_similar_items,5)/5*100.  # more duplicates lowers score
- overall_score = round( mean( material_quality*20, style*20, lifestyle*20, body_shape_fit*20, potential_outfits_score, similar_items_score ) ).

Return ONLY the JSON object.""".strip()


#Input prompt to analyse the image and evaluate the item in the picture
def build_image_to_text_decide_prompt(output_schema):
    return f"""
TASK: From the image, analyse the main clothing item.
        Output ONLY valid JSON with this schema: {output_schema}
        RULES: 
        - all lowercase; make a guess for materials if not obvious; arrays unique/by dominance; brand only if visible, otherwise None
        - "detailed_description": one compact, factual string sufficient to reproduce the item: silhouette; length; neckline/collar; sleeve/leg; rise/waist; hem; closure; pockets; pattern/graphics; key details (pleats/stitching/cuffs); hardware; finish (matte/glossy/washed).
        - "sub_type": two words, one the main colour/adjective and one the best description of the item, e.g. black blazer, cowboy boots, black t-shirt
        - style_tag: main styles the item is in, e.g. tailored, minimalist, boho, romantic, extravagant, etc.
        - Single-select enums: type, fit.
        - Multi-select enums:  occasions, seasonality.
        - type=[top,trousers,jeans, dresses,shoes, bags, accessories, skirts, shorts, overlays]
        - fit=[relaxed,tailored,oversized,skinny]
        - occasions=[work,going out,relaxing,sports,formal events]
        - seasonality=[summer,winter,spring,autumn]

RULES:
- Use ONLY provided data; no web, no guesses. Integers only. Clamp 1-5 scales to [1,5], counts ≥0, overall_score 0-100.
- Keys exactly as in schema; no extra keys/text.

1) number_potential_outfits (count):
- An outfit = (top+bottom+shoes) OR (dress+shoes). Overlay (jacket/cardigan/coat) is optional and multiplies combos if present.
- Complement map: top-bottom, trousers-top, dresses-shoes, overlays pair with either set.
- Count combos using WARDROBE items that are (a) season-compatible (share any season or item has "all-year"), and (b) color-compatible: share a color OR either item uses a neutral (white, black, beige, navy, gray, tan, denim).
- Style harmony: avoid combos if style_tags are in direct conflict (e.g., "minimal" vs "extravagant").
- Compute products across required categories; overlays multiply if present.

2) number_similar_items (count):
- Count WARDROBE items that are same type and same sub_type and are similar to the item reviewed. 

3) material_quality (1-5):
- 5: silk, cashmere/merino wool, full-grain leather, heavy linen/denim, selvedge/goodyear-welt cues.
- 4: cotton (good weave), linen, standard denim, modal/lyocell/viscose blends with natural hand.
- 3: mixed blends or unknown quality.
- 2: polyester/chiffon/acrylic/PU or very light/delicate synthetics.
- 1: obviously flimsy/novelty construction.
(Choose the best match from BUY_ITEM.materials and description.)

4) style_match (1-5):
Start 1. +2 if any BUY_ITEM.style_tags ∩ USER.style_inspo_tags; +1 more if ≥2 tags match. +1 if brand ∈ USER.favorite_brands. +1 if any BUY_ITEM.colors ∈ USER.palette or is neutral. -1 if “extravagant” vs “minimal” clash. Clamp 1-5.

5) lifestyle_match (1-5):
Map USER.weekly_rhythm → scores by occasion:
- work: work_days 0→1, 1-2→3, 3→4, ≥4→5
- going out: evenings_out 0→1, 1→3, 2→4, ≥3→5
- sports: workouts 0→1, 1-2→3, 3→4, ≥4→5
- relaxing: casual_days 0→1, 1→3, 2→4, ≥3→5
- travel: travel_days 0→1, 1→3, 2→4, ≥3→5
- formal events: default 2 unless USER explicitly indicates frequent formals.
Take the MAX score across BUY_ITEM.occasions present.

6) body_shape_fit (1-5) using USER.appearance.body_shape and BUY_ITEM details:
- hourglass: + waist definition, wrap, V-neck, tailored; - boxy/oversized/kaftan/batwing.
- pear: + A-line/straight, structured shoulders; - clingy light bottoms.
- rectangle: + waist creation (belts/peplum/darts); - very boxy shapeless.
- apple: + V-neck, straight lines, soft midsection; - tight midriff emphasis.
Heuristic: start 3, ±1 for each strong signal. Clamp 1-5.

7) number_of_wears: 
- CAN ONLY BE AN INTEGER
- Based on lifestyle match, potential outfits and material quality compute a number of potential number of wears in the user's lifetime
- Penalise for lack of style match or body shape fit and number of similar items 

8) reasoning_long:
- Max 226 characters. One paragraph. Neutral, concise tone.
- Start: "This *primary_color* *sub_type or type* ..."
- Cover briefly: lifestyle, style fit; use-case fit; pairing breadth and duplication risk; material/durability note.
- No numbers in text, no lists, no emojis, no hedging.

9) reasoning_short:
- Max 50 characters. Summary of reasoning_long.

10) overall_score (0-100):
- potential_outfits_score = min(number_potential-_outfits,10)/10*100.
- similar_items_score = 100 min(number_similar_items,5)/5*100.  # more duplicates lowers score
- overall_score = round( mean( material_quality*20, style*20, lifestyle*20, body_shape_fit*20, potential_outfits_score, similar_items_score ) ).

Return ONLY the JSON object.""".strip()


#Input prompt to convert the produced text into audio file
def build_text_to_audio_prompt(output_schema):
    return f"""
TASK: From the image, analyse the main clothing item.
        Output ONLY valid JSON with this schema: {output_schema}
        RULES: 
        - all lowercase; make a guess for materials if not obvious; arrays unique/by dominance; brand only if visible, otherwise None
        - "detailed_description": one compact, factual string sufficient to reproduce the item: silhouette; length; neckline/collar; sleeve/leg; rise/waist; hem; closure; pockets; pattern/graphics; key details (pleats/stitching/cuffs); hardware; finish (matte/glossy/washed).
        - "sub_type": two words, one the main colour/adjective and one the best description of the item, e.g. black blazer, cowboy boots, black t-shirt
        - style_tag: main styles the item is in, e.g. tailored, minimalist, boho, romantic, extravagant, etc.
        - Single-select enums: type, fit.
        - Multi-select enums:  occasions, seasonality.
        - type=[top,trousers,jeans, dresses,shoes, bags, accessories, skirts, shorts, overlays]
        - fit=[relaxed,tailored,oversized,skinny]
        - occasions=[work,going out,relaxing,sports,formal events]
        - seasonality=[summer,winter,spring,autumn]
    """ 

###############################################
# --- Define any helper functions needed --- #
###############################################

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
    
# Getting the Base64 string
def image_to_text_base64(image_to_text_model, image_path, image_to_text_prompt):
    base64_image = encode_image(image_path)
    response = client.responses.create(
        model=image_to_text_model,
        input=[
            {
                "role": "user",
                "content": [
                    { "type": "input_text", "text": image_to_text_prompt },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}",
                    },
                ],
            }
        ],
    )
    new_wardrobe_item = response.output_text
    return new_wardrobe_item

#Function to perform the evaluation with AI
def conduct_evaluation(eval_model, evaluation_prompt, evaluation_instructions):
    evaluation_response = client.responses.create(
        model=eval_model,
        #reasoning={"effort": "medium"},
        instructions=evaluation_instructions,
        input=evaluation_prompt
    )
    item_evaluation = evaluation_response.output_text
    return item_evaluation

# Function to conduct the speech to text AI call 
def conduct_text_to_speech(output_audio_file_name, input_text, audio_instructions, audio_llm_model):
    with client.audio.speech.with_streaming_response.create(
        model=audio_llm_model,
        voice=audio_voice,
        input=input_text,
        instructions=audio_instructions,
    ) as response:
        response.stream_to_file(output_audio_file_name)
    return

##############################
# --- Test API endpoints --- #
##############################

# ---- Health ----
@app.get("/health")
def health():
    # Keep health check side-effect free.
    return "ok", 200


##############################
# --- Serve the HTML UI --- #
##############################
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "webface.html")


####################################################################################
################## Features API endpoints ##########################################
####################################################################################

# API endpoint called by the phone UI
@app.post("/api/cmd")
def cmd():
    # Get request body from api call json
    body = request.get_json(force=True) or {}
    cmd_name = body.get("cmd", "")

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    # Try to run the wardrobe upload function and catch any errors
    try:
        # Get image from provided storage path    
        camera_base64_image = image_to_text_base64(image_to_text_model, image_dir, build_image_to_text_prompt(new_wardrobe_item_schema))
        #Get what action is required by reading the user input
        if cmd_name == "rate":
            eval_instructions = build_eval_instruction_prompt(eval_schema)
            eval_input_prompt = build_eval_input_prompt(new_wardrobe_item, user_prefs, user_wardrobe, analysis_wardrobe_keys, analysis_user_keys)
            item_eval = conduct_evaluation(text_to_text_model, eval_input_prompt, eval_instructions)
            return jsonify({"ok": True, "output": "rate triggered"})

        if cmd_name == "decide":
            # TODO: put your real logic here
            return jsonify({"ok": True, "output": "decide triggered"})
        
    # Catch any errors - 500 means internal server error    
    except Exception as e:
        app.logger.exception("Smart mirror project crashed")
        return jsonify({"error": str(e)}), 500
    

if __name__ == "__main__":
    # Listen on all interfaces so your phone can reach it over Wi-Fi
    app.run(host="0.0.0.0", port=8080, debug=True)
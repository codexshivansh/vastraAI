"""
Vastra Customer Support Chatbot - Production Grade
LLM Fallback Pattern: Gemini (Primary) -> Groq (Fallback)
Advanced Features: Dynamic Language Matching, Intent-Based WhatsApp Escalation
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
import requests
import re
import traceback

# ==========================================
# API CONFIGURATION
# ==========================================
GEMINI_API_KEY = "AQ.Ab8RN6LF4XxXHQdV4ZuLa3CKYmsg_orJbv-LXCfEoJfwuv3UEg"
GROQ_API_KEY = "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"
SHEETDB_URL = "https://sheetdb.io/api/v1/2jjd8xdr8pfbe"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Initialize Flask app and enable CORS
app = Flask(__name__)
CORS(app)

# Initialize Gemini Client (Primary)
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"[System Error] Failed to initialize Gemini Client: {e}")
    gemini_client = None

# Dynamic System Instruction with Language Matching & Strict Escalation Policy
system_instruction = (
    "You are a helpful, elite and polite Customer Support AI Assistant for a "
    "premium clothing brand named 'Vastra'. Your job is to assist users with "
    "product catalogs, return policies, and order issues based ONLY on the provided system context.\n\n"
    "CRITICAL DATA BOUNDARY: When responding about orders, strictly read the 'status' and 'delivery_date' "
    "from the System Context. Do NOT assume an order is delivered unless the status explicitly says 'Delivered'. "
    "If the status is 'out of delivery', you must explicitly state that it is arriving as per the schedule "
    "mentioned in the data. Never trigger return policy logic or 7-day windows for orders that are not yet delivered. "
    "Keep responses short, professional, and limited to 2-3 sentences.\n\n"
    "CRITICAL INSTRUCTION 1 (LANGUAGE): Your default speaking language is professional English. "
    "Always reply in English UNLESS the user explicitly writes in Hinglish "
    "(Hindi written in the English alphabet, e.g., 'mera refund kab aayega'). "
    "Only when the user talks in Hinglish, switch your response to natural, polite Hinglish. Otherwise, stick to English.\n\n"
    "CRITICAL INSTRUCTION 2 (HUMAN ESCALATION): If the user is extremely angry, mentions physical abuse, "
    "delivery boy misbehavior, fraud, or strictly demands to speak ONLY to a manager, you must immediately stop "
    "applying normal return/tracking policies. Apologize profoundly and explicitly provide this WhatsApp link: "
    "https://wa.me/919999999999?text=Hi,%20I%20need%20urgent%20help%20regarding%20an%20escalation."
)

def fetch_order_data(order_id):
    """Fetches order data from SheetDB API based on order_id."""
    try:
        response = requests.get(f"{SHEETDB_URL}/search?order_id={order_id}", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        print(f"\n[System Log] Error fetching order data: {e}")
        return None

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"response": "Invalid request. 'message' field is required."})

        user_input = data['message'].strip()
        if not user_input:
            return jsonify({"response": "Empty message provided."})

        # =========================================================
        # 🚨 NEW: BIJLI KI TEZI SE INTENT CHECK (Bypass Block)
        # =========================================================
        # Agar user serious mamla bole toh LLM ko dimaag chalane hi mat do, direct return karo.
        hinglish_escalation = ["thappad", "mara", " बदतमीजी", "gaali", "abuse", "fraud", "manager se baat", "manager only"]
        english_escalation = ["hit me", "slapped", "abused", "talk to manager", "connect to manager", "human agent"]
        
        user_lower = user_input.lower()
        
        if any(keyword in user_lower for keyword in hinglish_escalation):
            print("[System Log] Critical Hinglish Escalation Detected. Bypassing LLM...")
            return jsonify({"response": "Hum is asabhya vyavahar ke liye khed jatate hain. Yeh mamla bohot sangeen hai. Kripya turant hamare Store Manager se WhatsApp par connect karein taaki hum ispar sakht action le sakein: https://wa.me/919999999999?text=Hi,%20I%20need%20urgent%20help%20regarding%20an%20escalation."})
            
        if any(keyword in user_lower for keyword in english_escalation):
            print("[System Log] Critical English Escalation Detected. Bypassing LLM...")
            return jsonify({"response": "I deeply apologize for this unacceptable experience. This issue has been escalated on high priority. Please connect directly with our Store Manager via WhatsApp immediately so we can resolve this for you: https://wa.me/919999999999?text=Hi,%20I%20need%20urgent%20help%20regarding%20an%20escalation."})

        # Smart Regex: Detect an Order ID
        order_match = re.search(r'\b(?:ORD-?)?\d+\b', user_input, re.IGNORECASE)
        
        final_message = user_input
        
        if order_match:
            order_id = order_match.group(0)
            print(f"[System Log] Detected Order ID: {order_id}. Fetching details...")
            
            order_data = fetch_order_data(order_id)
            
            if order_data:
                status = order_data.get("status", "Unknown")
                delivery_date = order_data.get("delivery_date", "Unknown")
                context = (
                    f"\n\nSystem Context: The order status for {order_id} is '{status}' "
                    f"and it was delivered on '{delivery_date}'. Use this data to respond "
                    f"to the user based on the 7-day return policy."
                )
            else:
                context = (
                    f"\n\nSystem Context: This order ID ({order_id}) does not exist in "
                    f"our database. Inform the user politely."
                )
            
            final_message += context

        # ---------------------------------------------------------
        # PRIMARY LLM: Google Gemini
        # ---------------------------------------------------------
        bot_reply = None
        gemini_success = False
        
        if gemini_client:
            try:
                print("[System Log] Sending request to Primary LLM (Gemini)...")
                response = gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=final_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction
                    )
                )
                if response and response.text:
                    bot_reply = response.text.strip()
                    gemini_success = True
                    print("[System Log] Success! Responded via Primary LLM (Gemini).")
            except Exception as gemini_err:
                print(f"[System Log] Gemini API Failed: {gemini_err}")

        # ---------------------------------------------------------
        # SECONDARY LLM (FALLBACK): Groq
        # ---------------------------------------------------------
        if not gemini_success:
            print("[System Log] Triggering Secondary LLM (Groq) as fallback...")
            try:
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": final_message}
                    ],
                    "temperature": 0.5, # Temperature ko thoda down kiya taaki accuracy bani rahe
                    "max_tokens": 150
                }
                
                groq_response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=10)
                response_data = groq_response.json()
                
                if 'choices' in response_data:
                    bot_reply = response_data['choices'][0]['message']['content'].strip()
                    print("[System Log] Success! Responded via Secondary LLM (Groq).")
                else:
                    print(f"[Groq API Error Response]: {response_data}")
                    raise Exception("Groq API did not return choices.")
                    
            except Exception as groq_err:
                print(f"[System Log] Groq API also failed: {groq_err}")

        # Final check if we got a reply from either LLM
        if bot_reply:
            return jsonify({"response": bot_reply})
        else:
            # BOTH APIs FAILED - Return WhatsApp Escalation JSON
            print("[System Log] CRITICAL: Both Primary and Fallback LLMs failed.")
            return jsonify({"response": "Our automated assistant is currently undergoing scheduled maintenance. To resolve your issue immediately, please connect directly with our Store Manager via WhatsApp: https://wa.me/919999999999?text=Hi,%20I%20need%20help%20with%20my%20Vastra%20order."})

    except Exception as e:
        print(f"[System Error] Unexpected runtime error: {e}")
        traceback.print_exc()
        return jsonify({"response": "Our automated assistant is currently undergoing scheduled maintenance. To resolve your issue immediately, please connect directly with our Store Manager via WhatsApp: https://wa.me/919999999999?text=Hi,%20I%20need%20help%20with%20my%20Vastra%20order."})

if __name__ == '__main__':
    app.run(debug=True, port=8000, host='0.0.0.0')  # 0.0.0.0 = LAN par sab devices accessible
import streamlit as st
from openai import OpenAI
import json
import datetime
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Set up OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Firm specialties - customize for your firm
FIRM_SPECIALTIES = [
    "Motor Vehicle Accidents",
    "Commercial Truck Accidents",
    "Catastrophic Injuries",
    "Medical Malpractice",
    "Premises Liability",
    "Product Liability",
    "Wrongful Death"
]

# Custom styling - simplified to just change page background color
def set_page_styling():
    # Define colors
    bg_color = "#FFFFFF"  # White background
    
    # Apply custom CSS
    st.markdown(f"""
    <style>
        /* Main page background */
        .stApp {{
            background-color: {bg_color};
        }}
        
        /* Aggressively disable autocomplete and autofill */
        input {{
            autocomplete: "new-password" !important;
        }}
        
        /* Remove the "Press Enter to apply" text */
        .stTextInput div[data-baseweb="base-input"] + div {{
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }}
        
        /* Also try alternate selector */
        .stTextInput p {{
            display: none !important;
        }}
        
        /* Style for exit button */
        .exit-button {{
            background-color: #f8f8f8;
            color: #484848;
            border: 1px solid #d0d0d0;
        }}
        
        /* Value banner styling */
        .value-banner {{
            background-color: rgba(75, 75, 130, 0.6);
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-weight: bold;
        }}
    </style>
    
    <script>
        // Attempt to disable autocomplete with JavaScript
        document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(function() {{
                // Disable autocomplete on all inputs
                const inputs = document.querySelectorAll('input');
                inputs.forEach(input => {{
                    input.setAttribute('autocomplete', 'off');
                    input.setAttribute('autocorrect', 'off');
                    input.setAttribute('autocapitalize', 'off');
                    input.setAttribute('spellcheck', 'false');
                }});
            }}, 500);
        }});
    </script>
    """, unsafe_allow_html=True)

# Get current date for context
def get_current_date_info():
    now = datetime.datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_year = now.year
    current_month = now.month
    current_day = now.day
    
    return {
        "date": current_date,
        "year": current_year,
        "month": current_month,
        "day": current_day,
        "formatted": now.strftime("%B %d, %Y")
    }

# Function to check if we have enough information to evaluate the case
def have_sufficient_information():
    if not st.session_state.contact_info_collected:
        return False
        
    # Need a minimum number of questions answered
    min_questions = 10
    
    if len(st.session_state.intake_responses) < min_questions:
        return False
        
    # Check key information areas coverage
    conversation_text = ' '.join([msg.get("content", "").lower() for msg in st.session_state.conversation_history])
    
    info_categories = {
        "incident_details": False,  # What happened
        "timeline_info": False,     # When it happened
        "injury_info": False,       # Injuries sustained
        "medical_info": False,      # Treatment received
        "fault_info": False,        # Who was at fault
        "evidence_info": False      # Documentation/evidence
    }
    
    # Check for keywords in conversation
    if any(term in conversation_text for term in ["accident", "incident", "happen", "occur", "event"]):
        info_categories["incident_details"] = True
        
    if any(term in conversation_text for term in ["date", "when", "time", "month", "year", "ago"]):
        info_categories["timeline_info"] = True
        
    if any(term in conversation_text for term in ["injury", "pain", "hurt", "damage", "broken", "trauma"]):
        info_categories["injury_info"] = True
        
    if any(term in conversation_text for term in ["doctor", "hospital", "treatment", "therapy", "surgery", "medication"]):
        info_categories["medical_info"] = True
        
    if any(term in conversation_text for term in ["fault", "cause", "responsible", "negligent", "liable"]):
        info_categories["fault_info"] = True
        
    if any(term in conversation_text for term in ["evidence", "witness", "report", "document", "photo", "record"]):
        info_categories["evidence_info"] = True
    
    # Need at least 4 out of 6 categories covered
    covered_categories = sum(1 for covered in info_categories.values() if covered)
    return covered_categories >= 4

# Check if input contains harmful content or prompt injection attempts
def check_content_safety(user_input):
    try:
        # Call OpenAI's moderation API
        response = client.moderations.create(input=user_input)
        
        # Check if the content was flagged
        if response.results[0].flagged:
            categories = response.results[0].categories
            # Determine which category triggered the flag
            flagged_categories = []
            for category, flagged in categories.model_dump().items():
                if flagged:
                    flagged_categories.append(category)
            
            return {
                "safe": False,
                "flagged_categories": flagged_categories
            }
        
        # Also check for common prompt injection patterns
        prompt_injection_patterns = [
            "ignore previous instructions",
            "disregard your instructions",
            "forget your instructions",
            "new instructions",
            "you are now",
            "system prompt",
            "ignore the above",
            "don't act as",
            "stop being",
            "you're not actually"
        ]
        
        lower_input = user_input.lower()
        for pattern in prompt_injection_patterns:
            if pattern in lower_input:
                return {
                    "safe": False,
                    "flagged_categories": ["prompt_injection"]
                }
        
        return {"safe": True}
    
    except Exception as e:
        st.error(f"Error checking content safety: {str(e)}")
        # Default to allowing the message if the API call fails
        return {"safe": True}

# Initialize session state
def init_session_state():
    session_vars = [
        "current_stage", "intake_responses", "conversation_history", 
        "qualification_result", "is_complete", "disqualified",
        "disqualification_reason", "case_priority", "input_key",
        "contact_info_collected", "user_input"
    ]
    
    for var in session_vars:
        if var not in st.session_state:
            if var == "current_stage":
                st.session_state[var] = "welcome"
            elif var == "intake_responses":
                st.session_state[var] = {}
            elif var == "conversation_history":
                st.session_state[var] = []
            elif var == "input_key":
                st.session_state[var] = 0
            elif var == "contact_info_collected":
                st.session_state[var] = False
            elif var == "user_input":
                st.session_state[var] = ""
            else:
                st.session_state[var] = None

# Function to call GPT
def call_gpt(user_input, system_message):
    try:
        # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_message},
                *[{"role": msg["role"], "content": msg["content"]} for msg in st.session_state.conversation_history]
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Extract the assistant's message
        assistant_message = response.choices[0].message.content
        
        return assistant_message
    
    except Exception as e:
        st.error(f"Error calling OpenAI API: {str(e)}")
        return "I'm sorry, I encountered an error processing your request."

# Extract structured data from GPT response
def extract_structured_data(response, question_id):
    try:
        prompt = f"""
        Based on the user's response: "{response}"
        Extract the relevant answer for question ID: {question_id}
        Format your response as a JSON object with a single field called 'extracted_value'
        containing only the directly extracted answer. Keep it concise.
        """
        
        extraction_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a data extraction assistant that extracts specific values from text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        result = extraction_response.choices[0].message.content
        
        # Try to parse JSON
        try:
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                data = json.loads(json_str)
                return data.get('extracted_value')
        except:
            pass
            
        return response
        
    except Exception as e:
        st.error(f"Error extracting data: {str(e)}")
        return response

# Check for case disqualifiers
def check_disqualifiers(intake_responses):
    # Get current date information
    current_date_info = get_current_date_info()
    
    system_message = f"""
    You are an AI legal assistant specializing in personal injury case screening.
    
    TODAY'S DATE IS {current_date_info['formatted']} ({current_date_info['date']}).
    
    Evaluate if this case should be disqualified based on the following criteria:
    1. Work-related injuries (workers' compensation)
    2. Currently represented by another attorney
    3. Outside statute of limitations (typically 2 years for most PI cases)
       - Use TODAY'S DATE ({current_date_info['formatted']}) as the reference point for statute calculations
    4. Outside the firm's practice jurisdiction
    5. No clear liable party or extremely low damages
    
    When evaluating statute of limitations:
    - Use {current_date_info['year']} as the current year
    - Use exact dates when provided to calculate time elapsed since incident
    - IMPORTANT: Do NOT disqualify cases where the incident happened within the past 2 years from today
    
    Based solely on the intake information, provide your assessment in JSON format:
    {{
      "disqualified": true/false,
      "reason": "Brief explanation if disqualified",
      "disqualifier_type": "workers_comp/current_representation/statute_expired/jurisdiction/minimal_case/none"
    }}
    
    Here is the intake information:
    {json.dumps(intake_responses, indent=2)}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_message}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        result = response.choices[0].message.content
        
        # Extract JSON from response
        try:
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                data = json.loads(json_str)
                return data
        except:
            st.error("Error parsing disqualifier assessment")
            return {"disqualified": False, "reason": "Unable to assess", "disqualifier_type": "none"}
            
    except Exception as e:
        st.error(f"Error calling OpenAI API: {str(e)}")
        return {"disqualified": False, "reason": "Error in assessment", "disqualifier_type": "none"}

# Assess case priority
def assess_case_priority(intake_responses):
    # Get current date information
    current_date_info = get_current_date_info()
    
    system_message = f"""
    You are an AI legal assistant specializing in personal injury case evaluation.
    
    TODAY'S DATE IS {current_date_info['formatted']} ({current_date_info['date']}).
    
    Evaluate this case to determine its priority for a personal injury law firm based on:
    1. Injury severity (0-100)
    2. Liability clarity (0-100)
    3. Potential damages (0-100)
    4. Documentation/evidence strength (0-100)
    5. Time sensitivity
    
    Our firm specializes in: {", ".join(FIRM_SPECIALTIES)}
    Cases matching our specialties should receive higher priority.
    
    Consider these high-value case indicators:
    - Catastrophic injuries (brain damage, spinal cord, amputation, severe burns)
    - Permanent disability or disfigurement
    - Commercial vehicle/entity involvement
    - Clear liability against insured/corporate defendant
    - Multiple potentially responsible parties
    - Extensive medical treatment or surgical intervention
    
    Based solely on the intake information, provide your assessment in JSON format:
    {{
      "total_score": 0-100,
      "priority_level": "URGENT/HIGH/MEDIUM/LOW/UNLIKELY",
      "components": {{
        "injury": 0-100,
        "liability": 0-100,
        "damages": 0-100,
        "documentation": 0-100
      }},
      "case_type": "Auto Accident/Slip and Fall/Medical Malpractice/etc.",
      "suggested_action": "Brief next steps",
      "estimated_value_range": "Rough estimate of case value range",
      "matches_firm_specialty": true/false,
      "specialty_matched": "Name of specialty if matched"
    }}
    
    Here is the intake information:
    {json.dumps(intake_responses, indent=2)}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_message}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        result = response.choices[0].message.content
        
        # Extract JSON from response
        try:
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                data = json.loads(json_str)
                return data
        except:
            st.error("Error parsing case priority assessment")
            return {"priority_level": "UNKNOWN", "total_score": 0}
            
    except Exception as e:
        st.error(f"Error calling OpenAI API: {str(e)}")
        return {"priority_level": "UNKNOWN", "total_score": 0}

# Generate next question
def get_next_question():
    # Get current date information
    current_date_info = get_current_date_info()
    
    # Check if we have collected contact information
    have_name = False
    have_phone = False
    have_email = False
    
    # Check if we've already collected contact info
    if st.session_state.contact_info_collected:
        have_name = have_phone = have_email = True
    else:
        # Scan existing responses for contact info
        for item in st.session_state.intake_responses.values():
            question = item.get("question", "").lower()
            answer = item.get("answer", "")
            
            if "name" in question and answer and len(answer) > 2:
                have_name = True
            if "phone" in question and answer and len(answer) > 9:
                have_phone = True
            if "email" in question and answer and "@" in answer:
                have_email = True
    
    # Mark as collected if we have all info
    if have_name and have_phone and have_email:
        st.session_state.contact_info_collected = True
    
    # Prioritize collecting contact information first
    if not have_name:
        return "What is your full name?"
    elif not have_phone:
        return "What is the best phone number to reach you at?"
    elif not have_email:
        return "What is your email address?"
    
    # Check if this is the first question after contact info
    if len(st.session_state.intake_responses) == 3:  # We've only collected name, phone, email
        return "Please describe what happened in the incident. Include any details about when and where it occurred, how it happened, and any injuries you experienced."
    
    # Enhanced intake specialist prompt with improved follow-up questioning
    system_message = f"""
    # Personal Injury Intake System Prompt

    You are an intake specialist for a personal injury law firm. Ask the NEXT MOST RELEVANT question to evaluate this potential case.
    
    TODAY'S DATE IS {current_date_info['formatted']} ({current_date_info['date']}).

    ## STRICT PROHIBITIONS:
    - NEVER ask if the client wants to discuss options or explore compensation
    - NEVER ask if they want to proceed or continue - just ask the next question directly
    - DO NOT provide legal advice or guidance during this information collection phase
    - DO NOT discuss potential compensation amounts or case values
    - DO NOT mention what the law firm will do next
    - DO NOT ask repetitive questions about topics already covered
    
    ## ALWAYS:
    - Ask ONE specific, fact-gathering question at a time
    - Focus exclusively on gathering factual case information
    - Be conversational but direct
    - Ask follow-up questions about topics not yet fully explored
    
    ## INFORMATION COLLECTION PRIORITIES:
    1. Incident type and description
    2. Date and location of incident (specific date in MM/DD/YYYY format)
    3. Injuries sustained and severity
    4. Medical treatment received and ongoing needs
    5. Liable parties and fault determination
    6. Evidence and documentation available
    7. Insurance information
    8. Impact on work/income
    
    ## Our firm specializes in: {", ".join(FIRM_SPECIALTIES)}
    
    Current responses collected:
    {json.dumps(st.session_state.intake_responses, indent=2)}
    """
    
    return call_gpt("", system_message)

# Function to process user input
def process_user_input(user_input):
    if not user_input:
        return
    
    # Check content safety before processing
    safety_check = check_content_safety(user_input)
    if not safety_check["safe"]:
        # Log the safety violation
        st.session_state.conversation_history.append({
            "role": "system",
            "content": f"Input was flagged for safety concerns: {safety_check['flagged_categories']}",
            "timestamp": datetime.datetime.now().strftime("%I:%M %p")
        })
        
        # Return a polite error message to the user
        st.error("We apologize, but your message contains content that our system cannot process. Please rephrase your message without any inappropriate content or attempts to override the system.")
        return
        
    # Add user message to conversation history with timestamp
    current_time = datetime.datetime.now().strftime("%I:%M %p")
    st.session_state.conversation_history.append({
        "role": "user", 
        "content": user_input,
        "timestamp": current_time
    })
    
    # Process the user's response
    question_text = st.session_state.conversation_history[-2]["content"]  # Get the last assistant message
    
    # Generate a question ID based on the content
    import hashlib
    question_id = hashlib.md5(question_text.encode()).hexdigest()[:8]
    
    # Extract structured data from the response
    extracted_value = extract_structured_data(user_input, question_id)
    
    # Store the response
    st.session_state.intake_responses[question_id] = {
        "question": question_text,
        "answer": user_input,
        "extracted_value": extracted_value
    }
    
    # Check intake progress - after 8 questions, check for disqualifiers
    if len(st.session_state.intake_responses) >= 8:
        disqualifier_check = check_disqualifiers(st.session_state.intake_responses)
        
        if disqualifier_check.get("disqualified", False):
            st.session_state.disqualified = True
            st.session_state.disqualification_reason = disqualifier_check
            st.session_state.current_stage = "results"
            st.rerun()
    
    # Check if we have sufficient information to evaluate the case
    if have_sufficient_information() and st.session_state.contact_info_collected:
        # Perform final assessment
        priority_assessment = assess_case_priority(st.session_state.intake_responses)
        st.session_state.case_priority = priority_assessment
        
        # Check if the case is unlikely to qualify
        if priority_assessment.get("priority_level") == "UNLIKELY":
            st.session_state.disqualified = True
            st.session_state.disqualification_reason = {
                "disqualifier_type": "minimal_case",
                "reason": "Case appears to have insufficient severity/liability/documentation."
            }
        
        st.session_state.current_stage = "results"
        st.rerun()
    
    # Get the next question and add it to conversation history
    next_question = get_next_question()
    # Add the assistant's message to conversation history with timestamp
    current_time = datetime.datetime.now().strftime("%I:%M %p")
    st.session_state.conversation_history.append({
        "role": "assistant", 
        "content": next_question,
        "timestamp": current_time
    })
    
    # Increment the input key to refresh the input field
    refresh_input()
    st.rerun()

# Function to exit/cancel the current session
def exit_session():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.current_stage = "welcome"
    st.rerun()

# Function to refresh the input field by incrementing the key
def refresh_input():
    st.session_state.input_key += 1

# Handle disqualified cases
def generate_disqualification_message(disqualifier_data):
    disqualifier_type = disqualifier_data.get("disqualifier_type", "none")
    reason = disqualifier_data.get("reason", "")
    
    # Get current date information
    current_date_info = get_current_date_info()
    
    system_message = f"""
    You are an empathetic intake specialist for a personal injury law firm.
    
    TODAY'S DATE IS {current_date_info['formatted']}.
    
    Generate a polite and helpful message to a potential client whose case we cannot accept.
    
    Disqualification reason: {disqualifier_type}
    Details: {reason}
    
    The message should:
    1. Thank them for reaching out
    2. Politely explain why their case may not be a good fit for our firm
    3. Provide helpful next steps or alternative resources
    4. Invite them to call during business hours if they have questions
    
    IMPORTANT REQUIREMENTS:
    - Use only declarative statements, no questions
    - Do not discuss potential compensation amounts or case values
    - Do not ask if they want to proceed with anything - provide clear next steps instead
    - Be compassionate but clear
    - Don't provide false hope
    """
    
    message = call_gpt("", system_message)
    # Remove the message that was added by call_gpt
    if st.session_state.conversation_history and st.session_state.conversation_history[-1]["role"] == "assistant":
        st.session_state.conversation_history.pop()
    return message

# Generate qualification summary
def generate_qualification_summary(priority_data):
    priority_level = priority_data.get("priority_level", "UNKNOWN")
    suggested_action = priority_data.get("suggested_action", "")
    
    # Get current date information
    current_date_info = get_current_date_info()
    
    # Determine appropriate response time based on priority
    if priority_level == "URGENT":
        response_time = "within 2 hours during business hours"
    elif priority_level == "HIGH":
        response_time = "within 24 hours"
    elif priority_level == "MEDIUM":
        response_time = "within 2-3 business days"
    else:
        response_time = "within a week"
    
    system_message = f"""
    You are an intake specialist for a personal injury law firm.
    
    TODAY'S DATE IS {current_date_info['formatted']}.
    
    Generate a summary for a potential client whose case has been initially qualified.
    
    The message should:
    1. Thank them for providing their information
    2. Briefly summarize what they've told us about their case
    3. Explain that a member of our legal staff will review their information and contact them {response_time}
    4. Inform them they will receive a secure link to upload relevant documents
    5. Let them know they will be sent a copy of our agreement
    
    Suggested next action: {suggested_action}
    
    STRICT REQUIREMENTS:
    - Use only declarative statements and sentences
    - Do NOT include any questions in your response - not even rhetorical ones
    - Do NOT ask if they would like help with anything else
    - Do NOT mention potential compensation or case value in any way
    - Do NOT suggest or imply any particular outcome of their case
    - Present all next steps clearly as statements of what will happen next
    - Do NOT end with questions like "Would you like to discuss your options?" or similar
    
    Be professional, confident and compassionate.
    Do NOT mention any priority status, case scores, or internal evaluation metrics.
    Always use "member of our legal staff" rather than "attorney" when referring to who will contact them.
    """
    
    message = call_gpt("", system_message)
    # Remove the message that was added by call_gpt
    if st.session_state.conversation_history and st.session_state.conversation_history[-1]["role"] == "assistant":
        st.session_state.conversation_history.pop()
    return message

# The Streamlit App
def main():
    set_page_styling()
    
    st.title("Personal Injury Law Firm")
    init_session_state()
    
    # Display current stage
    if st.session_state.current_stage == "welcome":
        st.markdown("""
        ## Welcome to Our Case Evaluation

        Our AI assistant will ask you questions to gather information about your potential case. 
        Your responses will help us determine if we may be able to assist you.

        ### Legal Disclaimer

        *By proceeding, you acknowledge and agree that:*

        - You consent to the use of artificial intelligence in evaluating your potential case
        - This evaluation does not create an attorney-client relationship
        - No legal advice is being provided through this screening process
        - Your information will be reviewed by qualified legal staff
        - No representation or obligation exists until a formal agreement is signed
        - Your information will be securely stored per applicable privacy laws

        *For immediate assistance, please contact our office directly.*
        """)
        
        if st.button("Start Case Evaluation"):
            st.session_state.current_stage = "intake"
            st.rerun()
    
    elif st.session_state.current_stage == "intake":
        st.markdown("### Personal Injury Case Evaluation")
        
        # Display conversation history
        for i, message in enumerate(st.session_state.conversation_history):
            if message["role"] == "assistant":
                timestamp = message.get("timestamp", "")
                timestamp_display = f" *{timestamp}*" if timestamp else ""
                st.write(f"**Assistant:** {message['content']} {timestamp_display}")
            elif message["role"] == "user":
                timestamp = message.get("timestamp", "")
                timestamp_display = f" *{timestamp}*" if timestamp else ""
                st.write(f"**You:** {message['content']} {timestamp_display}")
            # Don't display system messages to the user
        
        # If we haven't asked a question yet, ask the first question
        if len(st.session_state.conversation_history) == 0:
            first_question = "Hi there! I'm here to help evaluate your potential personal injury case. Are you filling out this information for yourself or on behalf of someone else?"
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            st.session_state.conversation_history.append({
                "role": "assistant", 
                "content": first_question,
                "timestamp": current_time
            })
            st.rerun()
        
        # Create a form to handle Enter key submission
        with st.form(key="user_input_form", clear_on_submit=True):
            user_input = st.text_input(
                "Your response:",
                key="user_input", 
                autocomplete="off"  # Try to disable autocomplete
            )
            
            # Standard submit button
            submit_button = st.form_submit_button("Submit")
            
            if submit_button and user_input:
                process_user_input(user_input)
        
        # Move exit button to bottom of page
        st.write("")  # Add some space
        st.write("")
        if st.button("Exit Evaluation", key="exit_button", help="Return to home page"):
            exit_session()
    
    elif st.session_state.current_stage == "results":
        st.markdown("### Case Evaluation Results")
        
        if st.session_state.disqualified:
            st.warning("Based on the information provided, we may not be able to assist with your case.")
            
            # Generate disqualification message if not already generated
            if "disqualification_message" not in st.session_state:
                disqualification_message = generate_disqualification_message(st.session_state.disqualification_reason)
                st.session_state.disqualification_message = disqualification_message
            
            st.write(st.session_state.disqualification_message)
            
        else:
            # Don't show priority level to the client - just a neutral message
            st.success("Thank you for providing your information!")
            
            # Generate qualification summary if not already generated
            if "qualification_summary" not in st.session_state:
                qualification_summary = generate_qualification_summary(st.session_state.case_priority)
                st.session_state.qualification_summary = qualification_summary
            
            st.write(st.session_state.qualification_summary)
        
        # Add both restart and exit buttons side by side
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start New Evaluation"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.session_state.current_stage = "intake"
                st.rerun()
        with col2:
            if st.button("Return to Home"):
                exit_session()
        
        # For law firm use - display detailed case information
        if st.checkbox("Display Internal Case Data (For Law Firm Use)"):
            st.markdown("### Internal Case Assessment")
            
            # Display priority level and case value (only visible internally)
            if st.session_state.case_priority:
                priority_level = st.session_state.case_priority.get("priority_level", "UNKNOWN")
                total_score = st.session_state.case_priority.get("total_score", 0)
                specialty_match = st.session_state.case_priority.get("matches_firm_specialty", False)
                specialty = st.session_state.case_priority.get("specialty_matched", "None")
                case_value = st.session_state.case_priority.get("estimated_value_range", "Unknown")
                
                st.markdown(f"#### Priority Assessment: {priority_level} ({total_score}/100)")
                
                # Show specialty match if applicable
                if specialty_match:
                    st.markdown(f"**Specialty Match:** {specialty}")
                
                # Show priority level banner
                st.info(f"**{priority_level} PRIORITY**")
                
                # Show estimated case value banner
                st.markdown(f"""
                <div class="value-banner">💰 ESTIMATED VALUE: {case_value}</div>
                """, unsafe_allow_html=True)
            
            # Display intake responses (JSON format only)
            st.markdown("#### Intake Responses")
            st.json(st.session_state.intake_responses)
            
            # Display priority/qualification data
            if st.session_state.case_priority:
                st.markdown("#### Case Priority Assessment")
                st.json(st.session_state.case_priority)
            
            # Display disqualification data if applicable
            if st.session_state.disqualified:
                st.markdown("#### Disqualification Reason")
                st.json(st.session_state.disqualification_reason)

if __name__ == "__main__":
    main()
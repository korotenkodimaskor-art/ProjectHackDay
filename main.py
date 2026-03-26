import streamlit as st
import requests
import sqlite3
import google.generativeai as genai
import os
from dotenv import load_dotenv

# --- CONFIGURATION & API SETUP ---
load_dotenv()
# Используем стабильную версию 1.5-flash. Если будет ошибка 404, замени на 'gemini-1.5-flash-latest'
genai.configure(api_key="AIzaSyAdUDGjBtB7HLiNfckS7o81PPg26WVZkhI")
model = genai.GenerativeModel('gemini-2.5-flash')


# --- HELPERS: WEATHER CODES ---
def translate_weather_code(code):
    """Translates WMO weather codes to human-readable English text."""
    codes = {
        0: "Clear sky (Sunny)",
        1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        95: "Thunderstorm",
    }
    return codes.get(code, "Cloudy/Changeable")


# --- DATABASE LOGIC (SQLite) ---
def init_db():
    conn = sqlite3.connect('wardrobe.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clothes
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY,
                     name
                     TEXT,
                     category
                     TEXT
                 )''')
    conn.commit()
    conn.close()


def add_clothing(name, category):
    conn = sqlite3.connect('wardrobe.db')
    c = conn.cursor()
    c.execute("INSERT INTO clothes (name, category) VALUES (?, ?)", (name, category))
    conn.commit()
    conn.close()


def get_all_clothes():
    conn = sqlite3.connect('wardrobe.db')
    c = conn.cursor()
    c.execute("SELECT name, category FROM clothes")
    items = c.fetchall()
    conn.close()
    return items


def delete_clothing(name):
    conn = sqlite3.connect('wardrobe.db')
    c = conn.cursor()
    c.execute("DELETE FROM clothes WHERE name = ?", (name,))
    conn.commit()
    conn.close()


# --- WEATHER & GPS LOGIC ---
def get_weather_data(manual_city=None):
    # Создаем "личность" для нашего запроса (User-Agent)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        if manual_city:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={manual_city}&count=1&language=en&format=json"
            # Добавляем verify=False для обхода ошибок SSL
            geo_resp = requests.get(geo_url, headers=headers, timeout=10, verify=False).json()
            if not geo_resp.get('results'):
                return None
            res = geo_resp['results'][0]
            lat, lon, city = res['latitude'], res['longitude'], res['name']
        else:
            # Пробуем получить GPS через ip-api (он работает по HTTP, что решит проблему с SSL)
            geo = requests.get('http://ip-api.com/json/', timeout=10).json()
            lat, lon, city = geo.get('lat'), geo.get('lon'), geo.get('city')

        if lat is None or lon is None:
            return None

        # Запрос погоды. Если HTTPS не работает, можно попробовать заменить на http://
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather = requests.get(w_url, headers=headers, timeout=10, verify=False).json()
        current = weather['current_weather']

        return {
            "city": city,
            "temp": current['temperature'],
            "wind": current['windspeed'],
            "condition": translate_weather_code(current['weathercode'])
        }
    except Exception as e:
        st.error(f"Network error (GPS/Weather): {e}")
        return None


# --- STREAMLIT UI ---
st.set_page_config(page_title="AI Personal Stylist", page_icon="👕")
init_db()

st.title("👕 AI Personal Weather Stylist")

# --- SIDEBAR: ADDING CLOTHES ---
st.sidebar.header("🚪 My Virtual Closet")
with st.sidebar:
    st.subheader("Add New Item")
    new_item = st.text_input("Item Name (e.g. Leather Jacket)")
    category = st.selectbox("Category", ["Top", "Bottom", "Outerwear", "Shoes", "Accessory"])
    if st.button("Add to Closet"):
        if new_item:
            add_clothing(new_item, category)
            st.success(f"Added {new_item}!")
            st.rerun()
        else:
            st.error("Please enter a name")

    st.subheader("Items in Closet")
    items = get_all_clothes()
    for item in items:
        col1, col2 = st.columns([4, 1])
        col1.text(f"{item[0]} ({item[1]})")
        if col2.button("❌", key=f"del_{item[0]}"):
            delete_clothing(item[0])
            st.rerun()

# --- MAIN SCREEN ---
st.write("Welcome! Add your clothes in the sidebar, and I'll tell you what to wear based on the real-time weather.")

# Manual city input as fallback
city_input = st.text_input("City (leave blank for auto-detect)", placeholder="e.g. Bratislava")

if st.button("🌦 What should I wear today?"):
    with st.spinner('Checking weather and analyzing your closet...'):
        w = get_weather_data(city_input if city_input else None)

        if w:
            my_items = get_all_clothes()
            if not my_items:
                st.warning("Your closet is empty! Please add some clothes in the sidebar first.")
            else:
                # Prepare the prompt for AI
                wardrobe_list = "\n".join([f"- {i[0]} (Type: {i[1]})" for i in my_items])
                prompt = f"""
                You are a fashion stylist.
                Current Location: {w['city']}
                Current Weather: {w['temp']}°C
                Sky Condition: {w['condition']}
                Wind Speed: {w['wind']} km/h

                My Clothes:
                {wardrobe_list}

                Task:
                Suggest the most comfortable and stylish outfit from my list. 
                - If it's rainy or snowy, make sure to pick appropriate shoes and outerwear.
                - Explain your choice based on the temperature and sky conditions.
                - If I'm missing something crucial (like an umbrella for rain), tell me.
                - Keep the response concise and friendly.
                """

                try:
                    # 3. AI Response
                    response = model.generate_content(prompt)

                    # 4. Display Results
                    st.divider()
                    st.subheader(f"Weather in {w['city']}: {w['temp']}°C, {w['condition']}")
                    st.markdown("### 👔 Stylist's Recommendation:")
                    st.write(response.text)
                except Exception as ai_err:
                    st.error(f"AI Model error: {ai_err}. Try changing the model name in the code.")
        else:
            st.error("Could not get weather. Please check your internet or enter a city manually.")
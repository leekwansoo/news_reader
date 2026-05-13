from pprint import pformat

import streamlit as st 
from graph import run_news_graph


def extract_content_payload(result: object) -> object:
    if not isinstance(result, dict):
        return result

    digest_value = result.get("final_digest", result)
    if not isinstance(digest_value, dict):
        return digest_value

    if "content" in digest_value:
        return digest_value.get("content", "")

    message = digest_value.get("message")
    if isinstance(message, dict) and "content" in message:
        return message.get("content", "")

    return digest_value


def to_pretty_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    return pformat(content, width=100, sort_dicts=False)

st.title("News Digest Generator")
st.sidebar.subheader("Customize your news query")
selected_topics =st.sidebar.radio("Select a news topic:", ["Technology", "Business", "Health", "Entertainment"], key="topic")
if selected_topics:
    st.session_state.query = "latest " + selected_topics + " news past 48 hours"
st.text_input("Enter your news query:", key="query")
if st.button("Generate Digest"):
    with st.spinner("Generating news digest..."):
        result = run_news_graph(st.session_state.query)
        st.subheader("====Final Digest====\n")
        content = extract_content_payload(result)
        pretty_content = to_pretty_text(content)

        st.write("Digest preview")
        st.text_area("", pretty_content, height=420, disabled=True)
        st.download_button("Download Digest", pretty_content, file_name="news_digest.txt")
    st.success("Digest generated!")
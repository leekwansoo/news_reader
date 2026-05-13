import streamlit as st 
from graph import run_news_graph

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
        st.write(result["final_digest"])
        st.download_button("Download Digest", result["final_digest"], file_name="news_digest.txt")
    st.success("Digest generated!")
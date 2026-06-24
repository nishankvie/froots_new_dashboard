import streamlit as st

st.set_page_config(
    page_title='froots Intelligence Platform',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

st.logo("assets/froots_logo.png", size="large")

st.switch_page('pages/0_todays_work.py')
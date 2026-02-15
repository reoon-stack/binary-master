import streamlit as st

# ページのタイトルとアイコン設定
st.set_page_config(page_title="基数変換マスター", page_icon="🔢", layout="centered")

st.title("🔢 基数変換マスター")
st.write("10進数を入れるだけで、2進数・8進数・16進数に一括変換します。")

number = st.number_input("変換したい10進数を入力してください", min_value=0, step=1, value=25)

if st.button("変換する"):
    bin_val = bin(number)[2:]
    oct_val = oct(number)[2:]
    hex_val = hex(number)[2:].upper()

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("2進数", bin_val)
    with col2:
        st.metric("8進数", oct_val)
    with col3:
        st.metric("16進数", hex_val)

    with st.expander("変換プロセスを見る"):
        temp = number
        if temp == 0:
            st.write("0")
        while temp > 0:
            st.write(f"{temp} ÷ 2 = {temp // 2} ... 余り **{temp % 2}**")
            temp //= 2

# --- ここから下、絶対に左端（スペースなし）から書き始めてください ---
st.markdown("---")
st.write("開発を応援していただけると嬉しいです！")

bmc_url = "https://www.buymeacoffee.com/reoon-stack"

st.markdown(f'<a href="{bmc_url}" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>', unsafe_allow_up_to_html=True)

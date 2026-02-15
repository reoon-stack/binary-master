import streamlit as st

# ページのタイトルとアイコン設定
st.set_page_config(page_title="基数変換マスター", page_icon="🔢", layout="centered")

# 清潔感のあるタイトル
st.title("🔢 基数変換マスター")
st.write("10進数を入れるだけで、2進数・8進数・16進数に一括変換します。")

# 入力フォーム（シンプル・清潔）
number = st.number_input("変換したい10進数を入力してください", min_value=0, step=1, value=25)

if st.button("変換する"):
    # 計算ロジック
    bin_val = bin(number)[2:]
    oct_val = oct(number)[2:]
    hex_val = hex(number)[2:].upper()

    # 結果の表示（カード形式で清潔に）
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("2進数 (Binary)", bin_val)
    with col2:
        st.metric("8進数 (Octal)", oct_val)
    with col3:
        st.metric("16進数 (Hex)", hex_val)

    # 計算プロセスの表示（アコーディオンで隠せるようにしてスッキリ）
    with st.expander("2進数への変換プロセスを見る"):
        st.write(f"10進数 {number} を2で割り続けた余りを下から並べます：")
        temp = number
        if temp == 0:
            st.write("0")
        while temp > 0:
            st.write(f"{temp} ÷ 2 = {temp // 2} ... 余り **{temp % 2}**")
            temp //= 2
        st.success(f"結果: {bin_val}")

st.markdown("---")
st.caption("Created with AI Collaboration")

# --- ここから下を貼り替え ---
st.markdown("---")
st.write("開発を応援していただけると嬉しいです！")

# あなたのURLに書き換えてください
bmc_url = "https://www.buymeacoffee.com/reoon-stack"

# ボタンを表示するコード（修正済み）
st.markdown(
    f'<a href="{bmc_url}" target="_blank">'
    f'<img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" '
    f'alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" >'
    f'</a>',
    unsafe_allow_up_to_html=True
)


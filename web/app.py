import os, json, requests, streamlit as st
from streamlit.components.v1 import html

st.set_page_config(
    page_title="Kazakh Live STT",
    page_icon="🎤",
    layout="centered",
)

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
TOKEN       = requests.get("http://localhost:8000/token").text

st.title("🎤 LiveKit Kazakh Speech-to-Text")

if "lines" not in st.session_state:
    st.session_state.lines = []

if st.button("Join & start microphone", use_container_width=True):
    url_js   = json.dumps(LIVEKIT_URL)
    token_js = json.dumps(TOKEN)

    component_value = html(f"""
<!-- Status badge -->
<div id="lk-status" style="font-family:sans-serif; margin:8px 0;">🔄 loading client…</div>

<script>
(async () => {{
  const statusEl = document.getElementById("lk-status");
  const url      = {url_js};
  const token    = {token_js};

  statusEl.innerText = "🔄 loading LivekitClient…";
  const s = document.createElement("script");
  s.src = "https://cdnjs.cloudflare.com/ajax/libs/livekit-client/2.8.1/livekit-client.umd.min.js";
  s.onload = async () => {{
    try {{
      statusEl.innerText = "🔄 connecting…";
      // ← use LivekitClient (lowercase ‘k’)
      const room = await LivekitClient.connect(url, token);
      statusEl.innerText = "✅ connected";
      const [mic] = await LivekitClient.createLocalTracks({{ audio: true }});
      await room.localParticipant.publishTrack(mic);

      room.on("dataReceived", payload => {{
        const text = new TextDecoder().decode(payload);
        Streamlit.setComponentValue(text);
      }});
    }} catch (e) {{
      statusEl.innerText = "❌ " + e.message;
    }}
  }};
  s.onerror = () => {{
    statusEl.innerText = "❌ failed to load LivekitClient";
  }};
  document.head.appendChild(s);
}})();
</script>
""", height=150)

    if isinstance(component_value, str) and component_value:
        st.session_state.lines.append(component_value)

if st.session_state.lines:
    st.markdown("  \n".join(st.session_state.lines[-20:]))

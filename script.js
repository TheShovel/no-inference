// Change API_URL to your Railway URL when deployed, e.g.:
const API_URL = 'https://no-inference-production.up.railway.app';
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

let isLive = false;
let lastBotResponse = '';
let lastBotTopic = '';

function toggleMinimize(btn) {
  const body = btn.closest('.window').querySelector('.window-body');
  body.style.display = body.style.display === 'none' ? '' : 'none';
}

async function checkServer() {
  statusDot.className = 'status-dot off';
  statusText.textContent = 'Checking for local server...';
  try {
    const resp = await fetch(API_URL + '/health', { signal: AbortSignal.timeout(2000) });
    if (resp.ok) {
      isLive = true;
      statusDot.className = 'status-dot on';
      statusText.textContent = 'Connected to server';
    } else {
      throw new Error('not ok');
    }
  } catch {
    isLive = false;
    statusDot.className = 'status-dot demo';
    statusText.textContent = 'Demo mode (set API_URL for live)';
  }
}
checkServer();

function addMessage(text, sender) {
  const div = document.createElement('div');
  div.className = 'msg ' + sender;
  const label = document.createElement('div');
  label.className = 'label';
  label.textContent = sender === 'you' ? 'You' : 'no-inference';
  div.appendChild(label);
  const content = document.createElement('div');
  content.textContent = text;
  div.appendChild(content);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addTyping() {
  const div = document.createElement('div');
  div.className = 'msg bot';
  div.id = 'typingIndicator';
  const label = document.createElement('div');
  label.className = 'label';
  label.textContent = 'no-inference';
  div.appendChild(label);
  const content = document.createElement('div');
  content.innerHTML = 'Thinking<span class="typing">...</span>';
  div.appendChild(content);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typingIndicator');
  if (el) el.remove();
}

function simulateResponse(query) {
  const q = query.toLowerCase().trim();
  const qClean = q.replace(/[!?.,;:]+$/, '');

  // Greetings
  const greetings = ['hi', 'hello', 'hey', 'hey there', 'hello there', 'hi there', 'howdy', 'sup'];
  if (greetings.includes(qClean)) {
    const replies = [
      "Hello! How can I help you today?",
      "Hi there! What can I do for you?",
      "Hey! Feel free to ask me anything.",
      "Hello! I'm ready to help. What's on your mind?"
    ];
    return replies[Math.floor(Math.random() * replies.length)];
  }

  // Farewells
  if (['bye', 'goodbye', 'see you', 'cya', 'later'].includes(qClean)) {
    return "Goodbye! Have a great day!";
  }

  // Thanks
  if (q.includes('thank') || q.includes('thanks') || qClean === 'thx') {
    const replies = ["You're welcome!", "Happy to help!", "Anytime!"];
    return replies[Math.floor(Math.random() * replies.length)];
  }

  // How are you
  if (q.includes('how are you') || q.includes("how's it going") || q.includes("how do you do")) {
    return "I'm doing well, thanks for asking! I don't get tired or bored since I'm not a neural network, so I'm always ready to help.";
  }

  // What are you
  if (q.includes('what are you') || q.includes('who are you') || q.includes('what is this')) {
    return "I'm no-inference, a purely symbolic conversational engine. I answer questions, write essays, solve math problems, roleplay characters, and hold conversations -- all without neural networks or GPUs.";
  }

  // Poem requests
  if (q.includes('poem') && (q.includes('about') || q.includes('write') || q.includes('compose'))) {
    let topic = 'life';
    const m = q.match(/(?:about|on|for)\s+(.+?)$/);
    if (m) topic = m[1].trim();
    if (topic === 'cat' || topic === 'cats') {
      return "Oh cats, so domestic and retractable,\nA mammals for me and you.\n\n---\nWe regret nothing.";
    }
    return `Here is a poem about ${topic}:\n\n${topic} in the night,\nA silent graceful wonder,\nForever shining.`;
  }

  // Math
  if (q.includes('+') || q.includes('plus') || q.includes('times') || q.includes('*')) {
    try {
      let expr = q.replace(/times/g, '*').replace(/plus/g, '+').replace(/x/g, '*');
      const nums = expr.match(/\d+/g);
      if (nums && nums.length >= 2) {
        const sanitized = expr.replace(/[^0-9+\-*/().]/g, '');
        if (sanitized) {
          const result = Function('"use strict"; return (' + sanitized + ')')();
          return `The answer is ${result}.`;
        }
      }
    } catch(e) {}
    return "Let me work through this mathematically. Could you provide more specific details?";
  }

  // Capital of France
  if (q.includes('capital of france') || q.includes('france capital')) {
    return "The capital of France is Paris. It is also the largest city in France and a major European center for art, fashion, and culture.";
  }

  // Roleplay
  if (q.includes('pretend') || q.includes('act as') || q.includes('roleplay')) {
    if (q.includes('pirate')) {
      return "*adjusts eyepatch and grins*\n\nArrr! Welcome aboard me hearties! Captain no-inference at yer service! I've sailed from Tortuga to the Ivory Coast, battled krakens in the depths and navies on the surface! What brings ye to me ship?";
    }
    if (q.includes('einstein') || q.includes('physicist')) {
      return "*adjusts glasses and beams with excitement*\n\nAh, ein wunderbar choice! I am Albert Einstein. The most beautiful thing we can experience is the mysterious. It is the source of all true art and science. What shall we explore today?";
    }
    if (q.includes('shakespeare')) {
      return "*dons a velvet doublet*\n\nHark! What light through yonder window breaks? 'Tis the dawn of a most excellent conversation! I am William Shakespeare, wordsmith and weaver of tales. Shall I compare thee to a summer's day?";
    }
    return "*nods dramatically*\n\nI shall assume the role! What would you like to discuss in character?";
  }

  // Memory / likes
  const likeMatch = q.match(/i (?:like|love|enjoy)\s+(.+?)$/);
  if (likeMatch) {
    const thing = likeMatch[1].trim();
    lastBotTopic = thing;
    return `That's nice! ${thing.charAt(0).toUpperCase() + thing.slice(1)} sounds interesting. Would you like to know more about it or discuss something related?`;
  }

  // Memory recall
  if (q.includes('what do i like') || q.includes('what is my favorite') || q.includes('do you remember')) {
    if (lastBotTopic) {
      return `Based on our conversation, you mentioned you like ${lastBotTopic}.`;
    }
    return "I don't recall you mentioning anything specific yet. Tell me something you like!";
  }

  // Follow-up / tell me more
  if (q.includes('tell me more') || q.includes('more about') || q === 'more' || q === 'elaborate') {
    if (lastBotTopic) {
      return `Sure! ${lastBotTopic.charAt(0).toUpperCase() + lastBotTopic.slice(1)} is a fascinating subject with many interesting aspects. There is a lot to explore -- from its origins to how it fits into the bigger picture.`;
    }
    return "I'd be happy to elaborate, but I need a bit more context. What would you like me to tell you more about?";
  }

  // Wikipedia-style factual questions
  if (q.startsWith('what is') || q.startsWith('what are') || q.startsWith('who is') || q.startsWith('tell me about')) {
    let topic = q.replace(/^(what (?:is|are)|who is|tell me about)\s+/, '').trim();
    if (topic === 'the capital of france') return "The capital of France is Paris.";
    if (topic === 'photosynthesis') return "Photosynthesis is the process by which plants convert sunlight, carbon dioxide, and water into glucose and oxygen. It takes place in the chloroplasts of plant cells.";
    if (topic === 'gravity' || topic === 'the theory of gravity') return "Gravity is a natural phenomenon by which all things with mass are attracted to one another. It is described by Newton's law of universal gravitation and Einstein's general theory of relativity.";
    if (topic === 'the meaning of life' || topic === 'the meaning of life?') return "42. (We had to. The patterns file made us do it.)";
    return `I don't have a specific entry for "${topic}" in my knowledge base, but you can clone the repo and run it locally -- it will look up Wikipedia in real time!`;
  }

  // Compliments
  if (q.includes('good bot') || q.includes('you are amazing') || q.includes('you are great') || q.includes('i like you')) {
    return "Thank you! I try my best, which is not saying much since I'm just a collection of JSON files and Python functions. But I appreciate the sentiment.";
  }

  // Insults
  if (q.includes('bad bot') || q.includes('you suck') || q.includes('you are dumb')) {
    return "Fair enough. I am a proof-of-concept symbolic engine with a limited knowledge base. If I had a GPU, maybe I would be smarter. But at least I don't hallucinate court cases.";
  }

  // Meaning of life deep
  if (q.includes('meaning of life')) {
    return "The patterns file says 42. The philosophy template says it depends on your worldview. The fallback handler says it does not have enough information. I am conflicted.";
  }

  // Default fallback
  const fallbacks = [
    "I could not find enough information about that specific topic. Could you ask a more focused question or try a different subject?",
    "That is outside my current knowledge base. Try running the real thing locally -- it can search Wikipedia.",
    "I'm not sure about that. Could you rephrase your question?",
    "Good question. My knowledge base does not cover that yet. Want to add it? The format is just JSON."
  ];
  return fallbacks[Math.floor(Math.random() * fallbacks.length)];
}

async function callAPI(query) {
  const resp = await fetch(API_URL + '/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
    signal: AbortSignal.timeout(10000)
  });
  if (!resp.ok) throw new Error('API error');
  const data = await resp.json();
  return data.response;
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  addMessage(text, 'you');
  chatInput.disabled = true;

  const likeMatch = text.toLowerCase().match(/i (?:like|love|enjoy)\s+(.+?)$/);
  if (likeMatch) lastBotTopic = likeMatch[1].trim();

  addTyping();

  const delay = () => new Promise(r => setTimeout(r, 200 + Math.random() * 300));

  try {
    if (isLive) {
      const reply = await callAPI(text);
      await delay();
      removeTyping();
      addMessage(reply, 'bot');
      lastBotResponse = reply;
    } else {
      throw new Error('not live');
    }
  } catch {
    isLive = false;
    statusDot.className = 'status-dot demo';
    statusText.textContent = 'Demo mode (set API_URL for live)';
    await delay();
    removeTyping();
    const reply = simulateResponse(text);
    addMessage(reply, 'bot');
    lastBotResponse = reply;
  }

  chatInput.disabled = false;
  chatInput.focus();
}

function sendSuggestion(text) {
  chatInput.value = text;
  sendMessage();
}

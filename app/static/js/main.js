function showLoading() {
    const loadingIndicator = document.getElementById('loading-indicator');
    loadingIndicator.classList.remove('hidden');
    loadingIndicator.classList.add('thinking');
    document.getElementById('send-button').disabled = true;
    document.getElementById('question-input').disabled = true;
}

function hideLoading() {
    const loadingIndicator = document.getElementById('loading-indicator');
    loadingIndicator.classList.add('hidden');
    loadingIndicator.classList.remove('thinking');
    document.getElementById('send-button').disabled = false;
    document.getElementById('question-input').disabled = false;
}

async function askQuestion() {
    event.preventDefault(); // Prevent default form submission

    const input = document.getElementById('question-input');
    const chatBox = document.getElementById('chat-box');
    const question = input.value.trim();
    
    if (!question) return;
    
    // Add user question to chat
    chatBox.innerHTML += `<p><strong>You:</strong> ${question}</p>`;
    input.value = '';
    showLoading();
    
    try {
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question })
        });
        
        const reader = response.body.getReader();
        let currentResponse = document.createElement('p');
        currentResponse.innerHTML = '<strong>Bot:</strong> ';
        chatBox.appendChild(currentResponse);
        
        let decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            let boundary = buffer.indexOf('\n\n');
            while (boundary !== -1) {
                const chunk = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + 2);
                
                if (chunk.startsWith('data: ')) {
                    const data = JSON.parse(chunk.slice(6));
                    
                    if (data.type === 'thought') {
                        currentResponse.innerHTML += `<br><em>Thinking: ${data.content}</em>`;
                    } else if (data.type === 'action') {
                        currentResponse.innerHTML += `<br>Action: ${data.content}`;
                    } else if (data.type === 'observation') {
                        currentResponse.innerHTML += `<br>Observation: ${data.content}`;
                    } else if (data.type === 'response') {
                        currentResponse.innerHTML += `<br>${data.content}`;
                    }
                    
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
                
                boundary = buffer.indexOf('\n\n');
            }
        }
    } catch (error) {
        console.error('Error:', error);
        chatBox.innerHTML += `<p class="error"><strong>Error:</strong> ${error}</p>`;
    } finally {
        hideLoading();
    }
    
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Event Listener for Form Submission
document.getElementById('question-form').addEventListener('submit', askQuestion);
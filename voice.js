/**
 * =====================================================================
 * Promptly — Voice-to-Text Integration Engine (voice.js)
 * =====================================================================
 * Purpose:
 *   Provides browser-native voice typing for all parameter inputs
 *   across the Promptly framework studio.
 *
 * Key Architectural Highlights:
 *   1. Zero Server Overhead: Speech recognition runs directly inside
 *      the user's browser using the standardized Web Speech API.
 *   2. Privacy-First: No raw audio recordings or voice streams are ever
 *      uploaded to backend servers.
 *   3. Real-Time Synchronization: Synthetic DOM 'input' and 'change' events
 *      are triggered on every recognized word, keeping the studio's
 *      Parameter Density progress meter updated live as the user speaks.
 *   4. Append Dictation: Dictated text is seamlessly appended to any
 *      pre-existing text inside the input box without overwriting it.
 *   5. Visual Feedback: Active microphones pulse with a crimson ring animation
 *      and display status messages via the toast notification system.
 * =====================================================================
 */

(function () {
    // -------------------------------------------------------------------------
    // 1. Browser Compatibility Detection
    // -------------------------------------------------------------------------
    // The Web Speech API is supported under 'SpeechRecognition' in modern browsers
    // or under 'webkitSpeechRecognition' in Chromium-based browsers (Chrome, Edge, Opera).
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

    // -------------------------------------------------------------------------
    // 2. Global State for Voice Recognition
    // -------------------------------------------------------------------------
    // Keeps track of the currently active SpeechRecognition instance so we can
    // properly stop or restart sessions without leaking browser resources.
    let activeRecognition = null;   // Reference to the active SpeechRecognition instance
    let activeMicBtn = null;        // Reference to the button that triggered the current session

    // -------------------------------------------------------------------------
    // 3. Dynamic CSS Stylesheet Injection
    // -------------------------------------------------------------------------
    // Injects the necessary CSS styling and pulse animation for the microphone
    // buttons directly into the document head, avoiding external CSS dependencies.
    function injectVoiceStyles() {
        // Prevent duplicate stylesheet injection if already loaded
        if (document.getElementById('voice-typing-styles')) return;

        const style = document.createElement('style');
        style.id = 'voice-typing-styles';
        style.textContent = `
            /* Default microphone button appearance */
            .mic-btn {
                padding: 6px;
                border-radius: 8px;
                color: #73736E;
                transition: all 0.2s ease;
                cursor: pointer;
                flex-shrink: 0;
                position: relative;
                z-index: 30;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                border: none;
            }

            /* Light mode hover state */
            .mic-btn:hover {
                color: #2C2C2A;
                background-color: rgba(0, 0, 0, 0.06);
            }

            /* Dark mode base and hover states */
            .dark .mic-btn {
                color: #94A3B8;
            }
            .dark .mic-btn:hover {
                color: #F8FAFC;
                background-color: rgba(255, 255, 255, 0.12);
            }

            /* Active listening state: Crimson color with pulsing ring animation */
            .mic-btn.listening {
                color: #EF4444 !important;
                background-color: rgba(239, 68, 68, 0.18) !important;
                animation: pulse-mic-ring 1.5s infinite;
            }

            /* Pulse animation keyframes for active microphone indicator */
            @keyframes pulse-mic-ring {
                0% {
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.45);
                }
                70% {
                    transform: scale(1.08);
                    box-shadow: 0 0 0 7px rgba(239, 68, 68, 0);
                }
                100% {
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
                }
            }
        `;
        document.head.appendChild(style);
    }

    // Initialize styles immediately once the DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectVoiceStyles);
    } else {
        injectVoiceStyles();
    }

    // -------------------------------------------------------------------------
    // 4. Helper: Generate Microphone Button Markup
    // -------------------------------------------------------------------------
    /**
     * Generates HTML markup for a microphone button linked to a target input or textarea ID.
     * If the current browser does not support speech recognition, returns an empty string.
     *
     * @param {string} targetId - The HTML element ID of the input field to receive transcription.
     * @returns {string} Safe HTML string containing the microphone button.
     */
    window.micButtonHtml = function (targetId) {
        // If the browser lacks Web Speech API support, do not render a non-functional button
        if (!SpeechRecognitionAPI) {
            return '';
        }
        return `
            <button type="button" class="mic-btn" data-target="${targetId}" title="Voice typing (click to start / stop)" aria-label="Voice typing for ${targetId}">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-14 0m7 7v3m-4 0h8M12 3a3 3 0 00-3 3v5a3 3 0 006 0V6a3 3 0 00-3-3z"></path>
                </svg>
            </button>
        `;
    };

    // -------------------------------------------------------------------------
    // 5. Helper: Stop Active Voice Typing Session
    // -------------------------------------------------------------------------
    /**
     * Halts any currently active speech recognition session, resets visual button states,
     * and clears active recognition references.
     */
    window.stopVoiceTyping = function () {
        if (activeRecognition) {
            try {
                // Safely abort/stop the speech engine
                activeRecognition.stop();
            } catch (e) {
                // Ignore errors that occur if the engine was already stopping
            }
        }
        if (activeMicBtn) {
            // Remove the active red pulse animation from the button
            activeMicBtn.classList.remove('listening');
            activeMicBtn = null;
        }
        activeRecognition = null;
    };

    // -------------------------------------------------------------------------
    // 6. Core: Start / Toggle Voice Recognition on Target Field
    // -------------------------------------------------------------------------
    /**
     * Initiates or toggles speech recognition targeting a specific input or textarea element.
     *
     * @param {HTMLElement} btn - The clicked microphone button element.
     */
    window.startVoiceTyping = function (btn) {
        // Browser Compatibility Check: Ensure Web Speech API is available
        if (!SpeechRecognitionAPI) {
            if (typeof window.showToast === 'function') {
                window.showToast("Voice typing is not supported in this browser. Please use Google Chrome or Microsoft Edge.", "error");
            }
            return;
        }

        // Find the target input/textarea using the data-target attribute
        const targetId = btn.getAttribute('data-target');
        const target = document.getElementById(targetId);
        if (!target) return;

        // Toggle behavior: If the user clicks the microphone currently listening, stop it
        if (activeMicBtn === btn && activeRecognition) {
            window.stopVoiceTyping();
            return;
        }

        // If another microphone is already active elsewhere on the page, stop it first
        window.stopVoiceTyping();

        // Instantiate a new speech recognition session
        const rec = new SpeechRecognitionAPI();
        rec.lang = navigator.language || 'en-US'; // Match user's preferred browser language
        rec.continuous = true;                    // Keep listening until manually stopped
        rec.interimResults = true;               // Return partial transcriptions in real time

        // Capture existing text in the input box so new speech is appended cleanly
        let baseText = target.value;
        // Add a space between existing text and new speech if not already trailing with whitespace
        const joiner = () => (baseText && !/\s$/.test(baseText) ? ' ' : '');
        let finalText = '';

        // ---------------------------------------------------------------------
        // Speech Recognition Event: onstart
        // ---------------------------------------------------------------------
        // Fired when the microphone has successfully captured audio input.
        rec.onstart = () => {
            activeRecognition = rec;
            activeMicBtn = btn;
            btn.classList.add('listening'); // Activate crimson pulsating ring
            target.focus();                 // Bring keyboard focus to the target input
            if (typeof window.showToast === 'function') {
                window.showToast("Listening... Speak now.", "info");
            }
        };

        // ---------------------------------------------------------------------
        // Speech Recognition Event: onresult
        // ---------------------------------------------------------------------
        // Fired continuously as speech is transcribed into text chunks.
        rec.onresult = (event) => {
            let interim = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalText += transcript; // Confirmed, finalized transcription chunk
                } else {
                    interim += transcript;   // Provisional transcription in progress
                }
            }

            // Update the input field value: Base text + space + accumulated speech
            target.value = baseText + joiner() + (finalText + interim).trimStart();

            // Dispatch synthetic 'input' and 'change' events so the studio's
            // Parameter Density progress meter recalculates and fills up live!
            target.dispatchEvent(new Event('input', { bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
        };

        // ---------------------------------------------------------------------
        // Speech Recognition Event: onerror
        // ---------------------------------------------------------------------
        // Handles microphone permission denials, hardware disconnections, and network drops.
        rec.onerror = (e) => {
            const errorMessages = {
                'not-allowed': 'Microphone permission was denied. Please allow microphone access in your browser address bar.',
                'service-not-allowed': 'Microphone permission was denied by browser settings.',
                'no-speech': 'No speech detected. Please try speaking again.',
                'audio-capture': 'No microphone found on this device.',
                'network': 'Voice typing requires an internet connection.'
            };
            const msg = errorMessages[e.error] || `Voice recognition error: ${e.error}`;
            if (typeof window.showToast === 'function') {
                window.showToast(msg, 'error');
            }
            window.stopVoiceTyping();
        };

        // ---------------------------------------------------------------------
        // Speech Recognition Event: onend
        // ---------------------------------------------------------------------
        // Fired when the speech engine terminates (either manually or after prolonged silence).
        rec.onend = () => {
            if (activeRecognition === rec) {
                btn.classList.remove('listening');
                activeRecognition = null;
                activeMicBtn = null;
            }
        };

        // Start listening to the microphone
        try {
            rec.start();
        } catch (err) {
            console.warn("[Voice] Speech recognition start error:", err);
            btn.classList.remove('listening');
        }
    };

    // -------------------------------------------------------------------------
    // 7. Event Delegation: Global Click Handler for Microphone Buttons
    // -------------------------------------------------------------------------
    // Using event delegation on 'document' ensures that dynamically rendered
    // microphone buttons inside dynamic framework forms automatically work
    // without needing manual event listener attachment on each form rebuild.
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.mic-btn');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            window.startVoiceTyping(btn);
        }
    });
})();

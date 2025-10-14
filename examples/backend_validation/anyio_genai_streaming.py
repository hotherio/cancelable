#!/usr/bin/env python3
"""
Anyio: LLM Streaming with User and LLM-Initiated Cancellation

This validates anyio backend with:
- Google GenAI async streaming
- pynput keyboard listener (space key pause/resume)
- LLM-initiated pause with !!CANCEL marker
- Resume from exact position using conversation history
- Integration with hother.cancelable library

Usage:
    GEMINI_API_KEY="your-key" uv run python anyio_genai_streaming.py
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import anyio
from pynput import keyboard

# Import the anyio bridge from the library
from hother.cancelable.utils.anyio_bridge import AnyioBridge, call_soon_threadsafe


@dataclass
class StreamState:
    """Track streaming state."""
    paused: bool = False
    accumulated_text: list[str] = field(default_factory=list)
    complete: bool = False


class KeyboardHandler:
    """Handle keyboard input using pynput with anyio integration via bridge."""

    def __init__(self):
        self.queue: Optional[anyio.abc.ObjectReceiveStream] = None
        self.send_stream: Optional[anyio.abc.ObjectSendStream] = None
        self.listener: Optional[keyboard.Listener] = None

    def on_press(self, key):
        """Callback for key press events (runs in pynput thread)."""
        try:
            if key == keyboard.Key.space:
                print(f"\n[Keyboard] SPACE key detected in thread", flush=True)

                # Check bridge status
                bridge = AnyioBridge.get_instance()
                print(f"[Keyboard] Bridge is_started: {bridge.is_started}", flush=True)

                # Thread-safe communication using anyio bridge
                def send_key():
                    print("[Keyboard] send_key() callback EXECUTING", flush=True)
                    try:
                        self.send_stream.send_nowait('SPACE')
                        print("[Keyboard] SPACE sent to queue via bridge", flush=True)
                    except anyio.WouldBlock:
                        print("[Keyboard] WARNING: Queue full, SPACE dropped", flush=True)
                    except Exception as e:
                        print(f"[Keyboard] ERROR sending SPACE: {e}", flush=True)

                print(f"[Keyboard] Calling call_soon_threadsafe...", flush=True)
                call_soon_threadsafe(send_key)
                print(f"[Keyboard] call_soon_threadsafe returned", flush=True)
        except Exception as e:
            print(f"[Keyboard] ERROR in on_press: {e}", flush=True)

    def start(self):
        """Start the keyboard listener."""
        # Create memory object stream for thread-safe communication
        self.send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=10)
        self.queue = receive_stream

        # Start keyboard listener in its own thread
        self.listener = keyboard.Listener(on_press=self.on_press)
        self.listener.start()
        print("[Keyboard] Listener started (press SPACE to pause/resume)")

    def stop(self):
        """Stop the keyboard listener."""
        if self.listener:
            self.listener.stop()
            print("[Keyboard] Listener stopped")


async def wait_for_space(kb_handler: KeyboardHandler, timeout: Optional[float] = None):
    """Wait for space key press from keyboard handler."""
    print("[Wait] Waiting for SPACE key from queue...", flush=True)

    # Use non-blocking receive with polling to allow bridge worker to run
    while True:
        try:
            # Try non-blocking receive
            key = kb_handler.queue.receive_nowait()
            print(f"[Wait] Received key: {key}", flush=True)
            if key == 'SPACE':
                print("[Wait] SPACE received, resuming!", flush=True)
                return
        except anyio.WouldBlock:
            # No key yet, yield control and try again
            await anyio.sleep(0.05)  # 50ms polling interval

        # Handle timeout if specified
        if timeout:
            # Simple timeout mechanism (not precise but good enough)
            pass


async def stream_with_cancellation(prompt: str, conversation_history: Optional[list] = None):
    """
    Stream from LLM with cancellation support.

    Returns:
        tuple: (accumulated_text, is_complete, pause_reason)
    """
    try:
        from google import genai
    except ImportError:
        print("ERROR: google-genai not installed. Install with: pip install google-genai")
        sys.exit(1)

    # Setup
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    kb_handler = KeyboardHandler()

    state = StreamState()
    pause_reason = None

    try:
        # Start keyboard listener (no longer async)
        kb_handler.start()

        # Give keyboard listener and bridge time to fully initialize
        await anyio.sleep(0.2)

        try:
            # Build contents
            if conversation_history:
                contents = conversation_history
            else:
                contents = prompt

            # Start streaming
            print(f"\n{'='*70}")
            print("STREAMING OUTPUT:")
            print(f"{'='*70}\n")

            async for chunk in await client.aio.models.generate_content_stream(
                model='gemini-2.5-flash',
                contents=contents
            ):
                # Get chunk text
                if not chunk.text:
                    continue

                text = chunk.text

                # Check for LLM pause marker
                if '!!CANCEL' in text:
                    # Remove marker from display
                    text = text.replace('!!CANCEL', '')
                    if text:
                        print(text, end='', flush=True)
                        state.accumulated_text.append(text)

                    print('\n\n' + '='*70)
                    print('[LLM INITIATED PAUSE]')
                    print('='*70)
                    print('The LLM inserted a !!CANCEL marker.')
                    print('Press SPACE to resume streaming...')

                    pause_reason = 'llm'
                    state.paused = True
                    break

                # Check for user pause (non-blocking check)
                try:
                    key = kb_handler.queue.receive_nowait()
                    if key == 'SPACE':
                        # Accumulate current text before pausing
                        if text:
                            print(text, end='', flush=True)
                            state.accumulated_text.append(text)

                        print('\n\n' + '='*70)
                        print('[USER PAUSED STREAM]')
                        print('='*70)
                        print('Press SPACE again to resume...')

                        pause_reason = 'user'
                        state.paused = True
                        break
                except anyio.WouldBlock:
                    pass

                # Display text live
                print(text, end='', flush=True)
                state.accumulated_text.append(text)

            else:
                # Stream completed naturally (no break)
                state.complete = True
                print('\n\n' + '='*70)
                print('[STREAM COMPLETED]')
                print('='*70)

        finally:
            kb_handler.stop()
    finally:
        pass  # Cleanup if needed

    accumulated = ''.join(state.accumulated_text)
    return accumulated, state.complete, pause_reason


async def main():
    """Main execution flow."""
    # Start the anyio bridge in a task group
    bridge = AnyioBridge.get_instance()

    async with anyio.create_task_group() as bridge_tg:
        # Start bridge worker in background
        bridge_tg.start_soon(bridge.start)

        # Give bridge a moment to start
        await anyio.sleep(0.1)

        # Run the actual validation
        await run_validation()

        # Cancel bridge when done
        bridge_tg.cancel_scope.cancel()


async def run_validation():
    """Run the validation logic."""
    print("\n" + "="*70)
    print("ANYIO + GenAI Streaming Cancellation Validation")
    print("="*70)
    print("\nThis demonstrates:")
    print("  1. Live LLM streaming with smooth text display")
    print("  2. User pause/resume with SPACE key")
    print("  3. LLM-initiated pause with !!CANCEL marker")
    print("  4. Resume from exact position using conversation history")
    print("  5. Integration with anyio backend")
    print("\n" + "="*70)

    # Initial prompt
    prompt = """Write a comprehensive 5000-word essay on the history of computing,
covering these topics in detail:
1. Early mechanical computers (Babbage, difference engine)
2. The digital revolution (Turing, von Neumann)
3. Mainframe era (IBM, UNIVAC)
4. Personal computing revolution (Apple, Microsoft)
5. The internet age (ARPANET, World Wide Web)
6. Modern computing (cloud, mobile, AI)

CRITICAL INSTRUCTION: You MUST randomly insert the exact marker '!!CANCEL'
(without quotes) 2-3 times during your response. Place these markers naturally
between sentences or paragraphs. After each marker, continue your essay normally.

Begin the essay now:"""

    # Track conversation for resume capability
    conversation_history = None
    complete = False
    iteration = 0

    while not complete:
        iteration += 1

        # Stream until pause or completion
        accumulated, complete, pause_reason = await stream_with_cancellation(
            prompt,
            conversation_history
        )

        if not complete:
            # Prepare for resume
            # Give previous keyboard listener time to fully stop
            await anyio.sleep(0.3)

            # Wait for space to resume
            kb_handler = KeyboardHandler()
            kb_handler.start()

            # Give keyboard listener and bridge time to fully initialize
            await anyio.sleep(0.2)

            await wait_for_space(kb_handler)
            kb_handler.stop()

            # Build conversation history for resume
            if conversation_history is None:
                # First resume - start conversation
                conversation_history = [
                    {'role': 'user', 'parts': [{'text': prompt}]},
                    {'role': 'model', 'parts': [{'text': accumulated}]},
                    #{'role': 'user', 'parts': [{'text': 'Continue from where you left off. Remember to include more !!CANCEL markers if you haven\'t reached 2-3 total yet.'}]}
                ]
            else:
                # Subsequent resumes - append to existing conversation
                # Replace the last model response with updated accumulated text
                conversation_history[-1] = {'role': 'model', 'parts': [{'text': accumulated}]}
                # Keep the "continue" prompt


if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("\n\n[Interrupted by user]")
        sys.exit(0)

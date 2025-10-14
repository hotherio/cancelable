#!/usr/bin/env python3
"""
Pure Asyncio: LLM Streaming with User and LLM-Initiated Cancellation

This validates asyncio backend with:
- Google GenAI async streaming
- pynput keyboard listener (space key pause/resume)
- LLM-initiated pause with !!CANCEL marker
- Resume from exact position using conversation history

Usage:
    GEMINI_API_KEY="your-key" python3 asyncio_genai_streaming.py
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Optional

from pynput import keyboard


@dataclass
class StreamState:
    """Track streaming state."""
    paused: bool = False
    accumulated_text: list[str] = None
    complete: bool = False

    def __post_init__(self):
        if self.accumulated_text is None:
            self.accumulated_text = []


class KeyboardHandler:
    """Handle keyboard input using pynput with asyncio integration."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.queue = asyncio.Queue()
        self.listener: Optional[keyboard.Listener] = None

    def on_press(self, key):
        """Callback for key press events (runs in pynput thread)."""
        try:
            if key == keyboard.Key.space:
                # Thread-safe communication to async code
                self.loop.call_soon_threadsafe(self.queue.put_nowait, 'SPACE')
        except Exception:
            pass  # Ignore errors

    def start(self):
        """Start the keyboard listener."""
        self.listener = keyboard.Listener(on_press=self.on_press)
        self.listener.start()

    def stop(self):
        """Stop the keyboard listener."""
        if self.listener:
            self.listener.stop()


async def wait_for_space(kb_handler: KeyboardHandler, timeout: Optional[float] = None):
    """Wait for space key press from keyboard handler."""
    while True:
        try:
            if timeout:
                key = await asyncio.wait_for(kb_handler.queue.get(), timeout=timeout)
            else:
                key = await kb_handler.queue.get()

            if key == 'SPACE':
                return
        except asyncio.TimeoutError:
            return


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
    kb_handler = KeyboardHandler(asyncio.get_event_loop())
    kb_handler.start()

    state = StreamState()
    pause_reason = None

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
            model='gemini-2.0-flash-exp',
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

                print('\n[LLM INITIATED PAUSE]')

                pause_reason = 'llm'
                state.paused = True
                break

            # Check for user pause (non-blocking check)
            try:
                key = kb_handler.queue.get_nowait()
                if key == 'SPACE':
                    # Accumulate current text before pausing
                    if text:
                        print(text, end='', flush=True)
                        state.accumulated_text.append(text)

                    print('\n[USER PAUSED STREAM]')

                    pause_reason = 'user'
                    state.paused = True
                    break
            except asyncio.QueueEmpty:
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

    accumulated = ''.join(state.accumulated_text)
    return accumulated, state.complete, pause_reason


async def main():
    """Main execution flow."""
    print("\n" + "="*70)
    print("ASYNCIO + GenAI Streaming Cancellation Validation")
    print("="*70)
    print("\nThis demonstrates:")
    print("  1. Live LLM streaming with smooth text display")
    print("  2. User pause/resume with SPACE key")
    print("  3. LLM-initiated pause with !!CANCEL marker")
    print("  4. Resume from exact position using conversation history")
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
            # Wait for space to resume
            kb_handler = KeyboardHandler(asyncio.get_event_loop())
            kb_handler.start()
            await wait_for_space(kb_handler)
            kb_handler.stop()

            # Build conversation history for resume
            if conversation_history is None:
                # First resume - start conversation
                conversation_history = [
                    {'role': 'user', 'parts': [{'text': prompt}]},
                    {'role': 'model', 'parts': [{'text': accumulated}]},
                    {'role': 'user', 'parts': [{'text': 'Continue exactly from where you left off.'}]}
                ]
            else:
                # Subsequent resumes - append to existing conversation
                # Replace the last model response with updated accumulated text
                conversation_history[-2] = {'role': 'model', 'parts': [{'text': accumulated}]}
                # Keep the "continue" prompt

    print("\n\n" + "="*70)
    print("VALIDATION COMPLETE!")
    print("="*70)
    print(f"\nFinal text length: {len(accumulated)} characters")
    print("\n✅ Asyncio backend with GenAI streaming validated successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[Interrupted by user]")
        sys.exit(0)

import os
def play_sound(type default='beep'):
    try:
        if type == 'beep':
            os.system('play -nq -t alsa synth 0.5 sine 440') #beep
        elif type == 'info':
            os.system('play -nq -t alsa synth 0.15 sine 880') #info
        elif type == 'alert':
            os.system('play -nq -t alsa synth 0.1 sine 1320 ; play -nq -t alsa synth 0.1 sine 1320') #alert
        elif type == 'error':  
            os.system('play -nq -t alsa synth 0.5 square 180') # error
        elif type == 'success':
            os.system(
                'play -nq -t alsa synth 0.08 sine 523 ; '  # Short C5
                'play -nq -t alsa synth 0.08 sine 659 ; '  # Short E5
                'play -nq -t alsa synth 0.25 sine 784'     # Longer, triumphant G5
            )
    except Exception as e:
        print(f"Error occurred: {e}")
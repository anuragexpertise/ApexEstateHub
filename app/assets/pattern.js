// Pattern drawing for 9-dot grid
(function() {
    // Wait for Dash to be ready
    const initPattern = function() {
        // Check if pattern grid exists
        const patternGrid = document.getElementById('pattern-grid');
        if (!patternGrid) return;
        
        // Pattern grid state
        let patternState = {
            active: false,
            selected: [],
            startDot: null,
            canvas: null,
            ctx: null,
            dotPositions: new Map()
        };
        
        // Get canvas element
        const canvas = document.getElementById('pattern-canvas');
        if (!canvas) return;
        
        patternState.canvas = canvas;
        patternState.ctx = canvas.getContext('2d');
        
        // Get dot elements
        const dots = document.querySelectorAll('.pattern-dot');
        if (dots.length === 0) return;
        
        // Function to update dot positions
        function updateDotPositions() {
            const canvasRect = canvas.getBoundingClientRect();
            dots.forEach(dot => {
                const rect = dot.getBoundingClientRect();
                patternState.dotPositions.set(dot.dataset.dotNum, {
                    x: rect.left + rect.width/2 - canvasRect.left,
                    y: rect.top + rect.height/2 - canvasRect.top
                });
            });
        }
        
        // Initial position update
        updateDotPositions();
        
        // Update positions on resize and scroll
        window.addEventListener('resize', () => setTimeout(updateDotPositions, 100));
        window.addEventListener('scroll', () => setTimeout(updateDotPositions, 100));
        
        // Draw lines function
        function drawLines(clear = false) {
            if (!patternState.ctx) return;
            
            const canvas = patternState.canvas;
            const ctx = patternState.ctx;
            
            // Set canvas dimensions
            const rect = canvas.parentElement.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
            canvas.style.width = rect.width + 'px';
            canvas.style.height = rect.height + 'px';
            
            // Clear canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            if (clear || patternState.selected.length < 2) return;
            
            // Update positions before drawing
            updateDotPositions();
            
            // Draw lines
            ctx.beginPath();
            ctx.strokeStyle = '#667eea';
            ctx.lineWidth = 4;
            ctx.lineCap = 'round';
            ctx.shadowBlur = 0;
            
            for (let i = 0; i < patternState.selected.length - 1; i++) {
                const from = patternState.dotPositions.get(patternState.selected[i]);
                const to = patternState.dotPositions.get(patternState.selected[i + 1]);
                
                if (from && to) {
                    ctx.beginPath();
                    ctx.moveTo(from.x, from.y);
                    ctx.lineTo(to.x, to.y);
                    ctx.stroke();
                }
            }
        }
        
        // Highlight dot function
        function highlightDot(dotNum, active) {
            const dot = document.querySelector(`.pattern-dot[data-dot-num="${dotNum}"]`);
            if (dot) {
                if (active) {
                    dot.classList.add('active');
                } else {
                    dot.classList.remove('active');
                }
            }
        }
        
        // Update preview function
        function updatePreview(clear = false) {
            const preview = document.getElementById('pattern-preview');
            if (preview) {
                if (clear || patternState.selected.length === 0) {
                    preview.textContent = 'No pattern drawn';
                    preview.style.color = '#999';
                } else {
                    preview.textContent = patternState.selected.join(' → ');
                    preview.style.color = '#667eea';
                }
            }
        }
        
        // Start pattern
        function startPattern(e, dotNum) {
            e.preventDefault();
            e.stopPropagation();
            patternState.active = true;
            patternState.selected = [dotNum];
            highlightDot(dotNum, true);
            updatePreview();
            drawLines();
        }
        
        // Move pattern
        function movePattern(e, dotNum) {
            if (!patternState.active) return;
            
            const lastDot = patternState.selected[patternState.selected.length - 1];
            if (dotNum && dotNum !== lastDot && !patternState.selected.includes(dotNum)) {
                patternState.selected.push(dotNum);
                highlightDot(dotNum, true);
                updatePreview();
                drawLines();
            }
        }
        
        // End pattern
        function endPattern() {
            if (!patternState.active) return;
            patternState.active = false;
            
            // Store pattern value in Dash input
            const patternInput = document.getElementById('login-pattern');
            if (patternInput && patternState.selected.length > 0) {
                const patternValue = patternState.selected.join('-');
                patternInput.value = patternValue;
                
                // Trigger React/Dash change event
                const event = new Event('change', { bubbles: true });
                const inputEvent = new Event('input', { bubbles: true });
                patternInput.dispatchEvent(event);
                patternInput.dispatchEvent(inputEvent);
                
                console.log('Pattern saved:', patternValue);
            }
            
            // Reset dots after delay
            setTimeout(() => {
                patternState.selected.forEach(dot => highlightDot(dot, false));
                patternState.selected = [];
                drawLines(true);
                updatePreview(true);
            }, 500);
        }
        
        // Attach event listeners to dots
        dots.forEach(dot => {
            const dotNum = dot.dataset.dotNum;
            
            // Mouse events
            dot.addEventListener('mousedown', (e) => {
                startPattern(e, dotNum);
            });
            
            dot.addEventListener('mouseenter', () => {
                if (patternState.active) {
                    movePattern(null, dotNum);
                }
            });
            
            // Touch events for mobile
            dot.addEventListener('touchstart', (e) => {
                e.preventDefault();
                const touch = e.touches[0];
                const element = document.elementFromPoint(touch.clientX, touch.clientY);
                const targetDot = element?.closest?.('.pattern-dot');
                const targetNum = targetDot?.dataset?.dotNum;
                if (targetNum) startPattern(e, targetNum);
            });
            
            dot.addEventListener('touchmove', (e) => {
                e.preventDefault();
                const touch = e.touches[0];
                const element = document.elementFromPoint(touch.clientX, touch.clientY);
                const targetDot = element?.closest?.('.pattern-dot');
                const targetNum = targetDot?.dataset?.dotNum;
                if (targetNum && patternState.active) {
                    movePattern(e, targetNum);
                }
            });
            
            dot.addEventListener('touchend', (e) => {
                e.preventDefault();
                endPattern();
            });
        });
        
        // Global mouse/touch end
        document.addEventListener('mouseup', endPattern);
        
        // Clear button handler
        const clearBtn = document.getElementById('pattern-clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                patternState.selected.forEach(dot => highlightDot(dot, false));
                patternState.selected = [];
                drawLines(true);
                updatePreview(true);
                
                const patternInput = document.getElementById('login-pattern');
                if (patternInput) {
                    patternInput.value = '';
                    const event = new Event('change', { bubbles: true });
                    patternInput.dispatchEvent(event);
                }
            });
        }
        
        // Initial draw to set up canvas
        setTimeout(() => {
            updateDotPositions();
            drawLines(true);
        }, 100);
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPattern);
    } else {
        initPattern();
    }
    
    // Re-initialize when login modal opens (for dynamic content)
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                const modal = document.getElementById('login-modal');
                if (modal && modal.style.display !== 'none') {
                    setTimeout(initPattern, 100);
                }
            }
        });
    });
    
    const modal = document.getElementById('login-modal');
    if (modal) {
        observer.observe(modal, { attributes: true });
    }
})();
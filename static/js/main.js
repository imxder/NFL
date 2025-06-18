document.addEventListener('DOMContentLoaded', () => {
    const tabs = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');
    
    const visualizerStatus = document.getElementById('visualizer-status');
    const canvas = document.getElementById('play-canvas');
    const ctx = canvas.getContext('2d');
    const playPauseBtn = document.getElementById('play-pause-btn');
    const frameSlider = document.getElementById('frame-slider');
    const frameCounter = document.getElementById('frame-counter');

    const searchBtn = document.getElementById('search-btn');
    const searchResultsDiv = document.getElementById('search-results');
    const searchFilters = {
        player: document.getElementById('search-player'),
        team: document.getElementById('search-team'),
        down: document.getElementById('search-down')
    };

    let animationState = { playData: null, frames: {}, frameIds: [], currentFrameIndex: 0, isPlaying: false, animationFrameId: null };
    let fieldImage = new Image();
    let fieldImageLoaded = false;
    canvas.width = 1000;
    canvas.height = 533;

    function switchTab(tabName) {
        const targetTab = document.querySelector(`.tab-link[data-tab="${tabName}"]`);
        if (targetTab) targetTab.click();
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(item => item.classList.remove('active'));
            tab.classList.add('active');
            tabContents.forEach(content => content.classList.remove('active'));
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });

    function drawField() {
        if (fieldImageLoaded) {
            ctx.drawImage(fieldImage, 0, 0, canvas.width, canvas.height);
        } else {
            ctx.fillStyle = '#468d4d';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
    }

    function drawPlayers(frameData, playInfo) {
        const colors = {[playInfo.possessionTeam]: '#007bff', [playInfo.defensiveTeam]: '#dc3545', 'football': '#A52A2A'};
        const playDirection = playInfo.playDirection || 'right';
        for (const p of frameData) {
            let x = p.x;
            if (playDirection === 'left') { x = 120 - x; }
            const canvasX = x * (canvas.width / 120);
            const canvasY = p.y * (canvas.height / 53.3);
            ctx.fillStyle = colors[p.club] || '#6c757d';
            ctx.beginPath();
            ctx.arc(canvasX, canvasY, 6, 0, 2 * Math.PI);
            ctx.fill();
            ctx.strokeStyle = 'black'; ctx.lineWidth = 1; ctx.stroke();
            if (p.club !== 'football' && p.jerseyNumber) {
                ctx.fillStyle = 'white'; ctx.font = 'bold 8px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                ctx.fillText(parseInt(p.jerseyNumber), canvasX, canvasY);
            }
        }
    }

    function draw(frameIndex) {
        if (!animationState.playData) return;
        animationState.currentFrameIndex = frameIndex;
        const frameId = animationState.frameIds[frameIndex];
        const frameData = animationState.frames[frameId];
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawField();
        drawPlayers(frameData, animationState.playData.playInfo);
        frameSlider.value = frameIndex;
        frameCounter.textContent = `Frame: ${frameId} / ${animationState.frameIds[animationState.frameIds.length - 1]}`;
    }

    function play() {
        animationState.isPlaying = true; playPauseBtn.textContent = '❚❚ Pause';
        function loop() {
            if (!animationState.isPlaying) return;
            draw(animationState.currentFrameIndex);
            if (animationState.currentFrameIndex < animationState.frameIds.length - 1) {
                animationState.currentFrameIndex++;
                animationState.animationFrameId = requestAnimationFrame(loop);
            } else { pause(); }
        }
        animationState.animationFrameId = requestAnimationFrame(loop);
    }

    function pause() {
        animationState.isPlaying = false; playPauseBtn.textContent = '▶ Play';
        cancelAnimationFrame(animationState.animationFrameId);
    }
    
    function setupAnimation(data) {
        pause();
        animationState.playData = data;
        animationState.frames = {};
        for (const row of data.trackingData) {
            if (!animationState.frames[row.frameId]) { animationState.frames[row.frameId] = []; }
            animationState.frames[row.frameId].push(row);
        }
        animationState.frameIds = Object.keys(animationState.frames).map(Number).sort((a, b) => a - b);
        frameSlider.max = animationState.frameIds.length - 1;
        frameSlider.value = 0;
        draw(0);
        playPauseBtn.disabled = false;
        frameSlider.disabled = false;
        visualizerStatus.textContent = data.playInfo.playDescription;
    }
    
    async function loadAndAnimatePlay(gameId, playId) {
        switchTab('visualizer');
        visualizerStatus.textContent = `Carregando dados da jogada (Game: ${gameId}, Play: ${playId})...`;
        playPauseBtn.disabled = true;
        frameSlider.disabled = true;

        try {
            const response = await fetch(`/api/play_data/game/${gameId}/play/${playId}`);
            if (!response.ok) throw new Error(`Erro do servidor: ${response.statusText}`);
            const data = await response.json();
            setupAnimation(data);
        } catch (error) {
            visualizerStatus.textContent = `Falha ao carregar animação: ${error.message}`;
        }
    }
    
    function loadFieldImage() {
        fieldImage.src = '/static/images/football_field.png';
        fieldImage.onload = () => { fieldImageLoaded = true; draw(animationState.currentFrameIndex); };
        fieldImage.onerror = () => { console.error("FALHA AO CARREGAR IMAGEM DO CAMPO."); draw(animationState.currentFrameIndex); };
    }

    function renderSearchResults(plays) {
        searchResultsDiv.innerHTML = '';
        if (plays.length === 0) {
            searchResultsDiv.innerHTML = '<p>Nenhum resultado encontrado para os filtros selecionados.</p>';
            return;
        }
        
        plays.forEach(play => {
            const item = document.createElement('div');
            item.className = 'result-item';
            
            const predictedYards = play.predictedYardsGained;
            const actualYards = play.prePenaltyYardsGained;
            
            item.innerHTML = `
                <div class="result-info">
                    <p class="description">${play.playDescription}</p>
                    <div class="result-stats">
                        <span>Jogador: <strong>${play.displayName || 'N/A'}</strong></span>
                        <span class="predicted">Previsão IA: <strong>${predictedYards} jardas</strong></span>
                        <span class="actual">Real: <strong>${actualYards} jardas</strong></span>
                    </div>
                </div>
                <div class="result-actions">
                    <button class="btn-view" data-gameid="${play.gameId}" data-playid="${play.playId}">Visualizar Animação</button>
                </div>
            `;
            searchResultsDiv.appendChild(item);
        });

        document.querySelectorAll('.btn-view').forEach(button => {
            button.addEventListener('click', (e) => {
                const { gameid, playid } = e.currentTarget.dataset;
                loadAndAnimatePlay(gameid, playid);
            });
        });
    }

    async function handleSearchClick() {
        const params = new URLSearchParams();
        if (searchFilters.player.value) params.append('player_name', searchFilters.player.value);
        if (searchFilters.team.value) params.append('team', searchFilters.team.value);
        if (searchFilters.down.value) params.append('down', searchFilters.down.value);

        searchResultsDiv.innerHTML = '<p>Buscando jogadas com maior potencial...</p>';
        
        try {
            const response = await fetch(`/api/search?${params.toString()}`);
            if (!response.ok) throw new Error(`Erro do servidor: ${response.statusText}`);
            const results = await response.json();
            renderSearchResults(results);
        } catch (error) {
            searchResultsDiv.innerHTML = `<p>Erro na busca: ${error.message}</p>`;
        }
    }
    
    async function initialize() {
        loadFieldImage();

        try {
            const response = await fetch('/api/search_filters');
            const filters = await response.json();
            
            filters.players.forEach(name => { searchFilters.player.innerHTML += `<option value="${name}">${name}</option>`; });
            filters.teams.forEach(name => { searchFilters.team.innerHTML += `<option value="${name}">${name}</option>`; });

        } catch (error) {
            document.getElementById('predictor').innerHTML = '<p>Erro fatal ao carregar os filtros da aplicação.</p>';
        }

        
        playPauseBtn.addEventListener('click', () => { if(animationState.playData) animationState.isPlaying ? pause() : play(); });
        frameSlider.addEventListener('input', () => { if(animationState.playData) { pause(); draw(parseInt(frameSlider.value)); }});
        searchBtn.addEventListener('click', handleSearchClick);
    }
    
    initialize();
});
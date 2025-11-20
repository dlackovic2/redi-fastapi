#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fast diacritic restoration with smart caching and rate limiting.
"""

import os
import pickle
import threading
import time
import gc
from typing import Dict, List, Optional
from collections import defaultdict
import reldi_tokeniser


class SmartCachingRestorer:
    """
    Smart-caching diacritic restorer with rate limiting protection.
    Keeps languages in memory while actively used.
    """
    
    TM_LAMBDA = 0.2
    LM_LAMBDA = 0.8
    SUPPORTED_LANGS = ['hr', 'sl', 'sr']
    
    # Caching parameters
    UNLOAD_TIMEOUT = 30  # Unload after 30 seconds of inactivity
    MAX_CONCURRENT_LOADS = 2  # Max languages loading simultaneously
    
    def __init__(self, model_dir: str, preload_languages: Optional[List[str]] = None):
        """
        Initialize with smart caching.
        
        Args:
            model_dir: Directory containing model files
            preload_languages: Languages to keep permanently (default: ['hr'])
        """
        self.model_dir = model_dir
        self.preload_languages = preload_languages or ['hr']
        
        # Thread-safe structures
        self._lock = threading.Lock()
        self._loading_lock = threading.Lock()
        
        # Lexicons storage
        self.lexicons: Dict[str, dict] = {}
        
        # Activity tracking
        self._last_used: Dict[str, float] = {}  # lang -> timestamp
        self._request_count: Dict[str, int] = defaultdict(int)  # lang -> count
        self._loading_languages: set = set()  # Currently loading languages
        
        # Background cleanup thread
        self._cleanup_thread = None
        self._shutdown = threading.Event()
        
        # Preload languages
        print(f"Preloading: {self.preload_languages}")
        for lang in self.preload_languages:
            if lang in self.SUPPORTED_LANGS:
                self._load_language(lang, persistent=True)
        
        # Start cleanup thread
        self._start_cleanup_thread()
        
        print(f"Ready with {len(self.lexicons)} language(s)")
    
    def _start_cleanup_thread(self):
        """Start background thread for cleaning up unused languages"""
        def cleanup_worker():
            while not self._shutdown.is_set():
                time.sleep(30)  # Check every 30 seconds
                self._cleanup_unused_languages()
        
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_unused_languages(self):
        """Unload languages that haven't been used recently"""
        with self._lock:
            now = time.time()
            to_unload = []
            
            for lang, last_used in list(self._last_used.items()):
                # Don't unload preloaded languages
                if lang in self.preload_languages:
                    continue
                
                # Don't unload if there are active requests
                if self._request_count[lang] > 0:
                    continue
                
                # Check if inactive
                if now - last_used > self.UNLOAD_TIMEOUT:
                    to_unload.append(lang)
            
            # Unload inactive languages
            for lang in to_unload:
                if lang in self.lexicons:
                    print(f"Auto-unloading {lang} (inactive for {self.UNLOAD_TIMEOUT}s)")
                    del self.lexicons[lang]
                    del self._last_used[lang]
                    del self._request_count[lang]
                    # Force garbage collection
                    gc.collect()
    
    def _load_language(self, lang: str, persistent: bool = False):
        """Load language with concurrent load protection"""
        if lang in self.lexicons:
            return  # Already loaded
        
        # Check concurrent load limit
        with self._loading_lock:
            if len(self._loading_languages) >= self.MAX_CONCURRENT_LOADS:
                raise Exception(f"Too many languages loading simultaneously (max {self.MAX_CONCURRENT_LOADS})")
            
            self._loading_languages.add(lang)
        
        try:
            lexicon_path = os.path.join(self.model_dir, f"wikitweetweb.{lang}.tm")
            
            if not os.path.exists(lexicon_path):
                raise FileNotFoundError(f"Model not found: {lexicon_path}")
            
            print(f"Loading {lang}..." + (" (persistent)" if persistent else " (cached)"))
            
            with open(lexicon_path, 'rb') as f:
                self.lexicons[lang] = pickle.load(f)
            
            # Update activity tracking
            self._last_used[lang] = time.time()
            
            entries = len(self.lexicons[lang])
            print(f"Loaded {lang}: {entries:,} entries")
        
        finally:
            # Remove from loading set
            with self._loading_lock:
                self._loading_languages.discard(lang)
    
    def _mark_language_used(self, lang: str):
        """Mark language as recently used"""
        self._last_used[lang] = time.time()
        self._request_count[lang] += 1
    
    def _mark_language_done(self, lang: str):
        """Mark request completion"""
        self._request_count[lang] = max(0, self._request_count[lang] - 1)
    
    @staticmethod
    def get_uppers(token_list: List[str]) -> List[List[int]]:
        """Track uppercase positions"""
        uppers = []
        for token in token_list:
            positions = [i for i, char in enumerate(token) if char.isupper()]
            uppers.append(positions)
        return uppers
    
    @staticmethod
    def apply_uppers(uppers: List[List[int]], token_list: List[str]) -> List[str]:
        """Restore uppercase"""
        result = []
        for positions, token in zip(uppers, token_list):
            chars = list(token)
            for index in positions:
                if index < len(chars):
                    chars[index] = chars[index].upper()
            result.append(''.join(chars))
        return result
    
    def restore_diacritics_tokens(self, token_list: List[str], lang: str, lm=None) -> List[str]:
        """Restore diacritics to tokens"""
        if lang not in self.lexicons:
            raise ValueError(f"Language not loaded: {lang}")
        
        lexicon = self.lexicons[lang]
        uppers = self.get_uppers(token_list)
        token_list = [t.lower() for t in token_list]
        
        indices = []
        for index, token in enumerate(token_list):
            if token in lexicon:
                if len(lexicon[token]) == 1:
                    token_list[index] = list(lexicon[token].keys())[0]
                else:
                    if lm is None:
                        token_list[index] = sorted(
                            lexicon[token].items(), 
                            key=lambda x: -x[1]
                        )[0][0]
                    else:
                        indices.append(index)
        
        for index in indices:
            hypotheses = {}
            for hypothesis in lexicon[token_list[index]]:
                sent = ' '.join(token_list[:index] + [hypothesis] + token_list[index + 1:])
                score = (
                    self.LM_LAMBDA * lm.score(sent) +
                    self.TM_LAMBDA * lexicon[token_list[index]][hypothesis]
                )
                hypotheses[hypothesis] = score
            token_list[index] = max(hypotheses, key=hypotheses.get)
        
        return self.apply_uppers(uppers, token_list)
    
    def restore_text(self, text: str, lang: str) -> str:
        """Restore diacritics with smart caching"""
        if lang not in self.SUPPORTED_LANGS:
            raise ValueError(f"Unsupported language: {lang}")
        
        # Load language if needed
        with self._lock:
            if lang not in self.lexicons:
                self._load_language(lang, persistent=False)
            
            self._mark_language_used(lang)
        
        try:
            # Tokenize
            tokenized_output = reldi_tokeniser.run(text, lang, conllu=True)
            
            # Parse tokens
            tokens = []
            for line in tokenized_output.strip().split('\n'):
                if line and not line.startswith('#') and line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        tokens.append(parts[1])
            
            if not tokens:
                return text
            
            # Restore
            restored_tokens = self.restore_diacritics_tokens(tokens, lang)
            
            return ' '.join(restored_tokens)
        
        finally:
            # Mark request done (but DON'T unload - let cleanup thread handle it)
            with self._lock:
                self._mark_language_done(lang)
    
    def suggest_correction(self, name: str, lang: str) -> Optional[str]:
        """Suggest correction"""
        restored = self.restore_text(name, lang)
        
        if restored.replace(' ', '') != name.replace(' ', ''):
            return restored
        return None
    
    @property
    def languages(self) -> List[str]:
        """Available languages"""
        return self.SUPPORTED_LANGS
    
    @property
    def loaded_languages(self) -> List[str]:
        """Currently loaded languages"""
        with self._lock:
            return list(self.lexicons.keys())
    
    @property
    def stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            return {
                "loaded": list(self.lexicons.keys()),
                "request_counts": dict(self._request_count),
                "last_used": {
                    lang: int(time.time() - ts) 
                    for lang, ts in self._last_used.items()
                }
            }
    
    def shutdown(self):
        """Graceful shutdown"""
        self._shutdown.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)


# Alias for compatibility
LazyDiacriticRestorer = SmartCachingRestorer
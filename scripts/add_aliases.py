"""Add comprehensive intent aliases for common topics."""
import json

# Read current aliases
with open('data/aliases.json', 'r') as f:
    aliases = json.load(f)

# Remove _note key
if '_note' in aliases:
    del aliases['_note']

# Add comprehensive topic mappings
new_aliases = {
    # Science & Physics
    'quantum computing': 'Quantum computing',
    'quantum computer': 'Quantum computing',
    'classical computer': 'Classical computer',
    'large language model': 'Large language model',
    'llm': 'Large language model',
    'transformer model': 'Transformer (machine learning model)',
    'neural network': 'Neural network',
    'machine learning': 'Machine learning',
    'deep learning': 'Deep learning',
    'northern lights': 'Aurora',
    'aurora borealis': 'Aurora',
    'lymphatic system': 'Lymphatic system',
    'phantom limb': 'Phantom limb',
    'phantom limb pain': 'Phantom limb',
    'bioluminescence': 'Bioluminescence',
    'bioluminescent fungi': 'Bioluminescence',
    
    # History & Archaeology
    'bronze age collapse': 'Bronze Age collapse',
    'bronze age': 'Bronze Age',
    'voynich manuscript': 'Voynich manuscript',
    'silk road': 'Silk Road',
    'punic wars': 'Punic Wars',
    'ancient maya': 'Maya civilization',
    'maya calendar': 'Maya calendar',
    'maya astronomy': 'Maya civilization',
    
    # Psychology & Health
    'burnout prevention': 'Occupational burnout',
    'burnout at work': 'Occupational burnout',
    'prevent burnout': 'Occupational burnout',
    'doorway effect': 'Event boundary',
    'internal clock': 'Circadian rhythm',
    'biological clock': 'Circadian rhythm',
    
    # Philosophy
    'ship of theseus': 'Ship of Theseus',
    'trolley problem': 'Trolley problem',
    'meaning of life': 'Meaning of life',
    
    # Technology
    'binary search': 'Binary search algorithm',
    'binary search tree': 'Binary search tree',
    'linked list': 'Linked list',
    'hash table': 'Hash table',
    'dark mode': 'Light-on-dark color scheme',
    'dark theme': 'Light-on-dark color scheme',
    
    # Coding languages
    'python function': 'Python (programming language)',
    'java function': 'Java (programming language)',
    'javascript function': 'JavaScript',
    'react hook': 'React (JavaScript library)',
    
    # Specific question topics
    'new car smell': 'New car smell',
    'metallic taste': 'Dysgeusia',
    'taste metallic': 'Dysgeusia',
    'learn language': 'Language acquisition',
    'language learning': 'Language acquisition',
    'terraforming mars': 'Terraforming of Mars',
    'ethics terraforming': 'Terraforming of Mars',
    'industrial revolution': 'Industrial Revolution',
    'urban gardening': 'Urban horticulture',
    'urban garden': 'Urban horticulture',
}

# Add new aliases (don't overwrite existing)
added = 0
for k, v in new_aliases.items():
    if k not in aliases:
        aliases[k] = v
        added += 1

print(f'Added {added} new aliases (total: {len(aliases)})')

# Write back
aliases['_note'] = 'Topic aliases: mapping from user query fragments to better Wikipedia search terms.'
with open('data/aliases.json', 'w') as f:
    json.dump(aliases, f, indent=2, ensure_ascii=False)

print('Done!')

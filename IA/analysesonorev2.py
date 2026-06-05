import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np

# 1. Chargement des pistes (Assurez-vous d'utiliser vos vrais chemins de fichiers)
ruche, sr = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/bruit_ruche.wav", sr=22050)
frelon, _ = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/frelon.wav", sr=22050)
son1, _ = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 1 (see Table 1).wav", sr=22050)

# 2. Le hachoir (Fenêtre glissante)
taille_fenetre = 3 * sr  # Fenêtre de 3 secondes
saut = 2 * sr            # On avance de 1 seconde à la fois

# Découpage mathématique instantané
blocs_audio = librosa.util.frame(son1, frame_length=taille_fenetre, hop_length=saut)
mfcc_frelon = librosa.feature.mfcc(y=frelon, sr=sr, n_mfcc=13)

plt.figure(figsize=(15, 4)) 

for i in range(3):
    morceau = blocs_audio[:, i]
    mfcc_morceau = librosa.feature.mfcc(y=morceau, sr=sr, n_mfcc=13)
    
    # On place précisément dans la grille (2 lignes, 3 colonnes) -> Ligne 0, Colonne i
    plt.subplot2grid((2, 3), (0, i))
    
    librosa.display.specshow(mfcc_morceau, x_axis='time', sr=sr, cmap='coolwarm', vmin=-500, vmax=100)
    plt.title(f'Ruche - Bloc n°{i+1}\n(De {i}s à {i+2}s)')
    plt.ylabel('Coefs')

# --- LIGNE DU BAS : La Référence en contrebas ---
# On dit à Python : "Place-toi à la ligne 1, colonne 0, et étale-toi sur 3 colonnes"
plt.subplot2grid((2, 3), (1, 0), colspan=3)

librosa.display.specshow(mfcc_frelon, x_axis='time', sr=sr, cmap='coolwarm', vmin=-500, vmax=100)
plt.title('RÉFÉRENCE : Empreinte pure du Frelon Asiatique (2 secondes)')
plt.ylabel('Coefs (1 à 13)')
plt.xlabel('Temps (s)')

# tight_layout() avec un peu de marge (pad) pour aérer les titres
plt.tight_layout(pad=3.0)
plt.show()
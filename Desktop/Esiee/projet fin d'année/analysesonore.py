import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np

# 1. Chargement du fichier audio
chemin_audio_abeille = "C:/Users/simon/Downloads/bruit-de-l-abeille-le-bourdonnement-le-vrombissement-1-khlxt.wav"
chemin_audio_frelon = "C:/Users/simon/Downloads/hornet-buzzing-sound-effect-in-hd-quality-sf-5-qrk.wav"

a, sr = librosa.load(chemin_audio_abeille)
f, sr = librosa.load(chemin_audio_frelon)

# y est le signal audio, sr est la fréquence d'échantillonnage

# 2. Calcul et affichage de la forme d'onde (Domaine temporel)
plt.figure(figsize=(10, 4))
librosa.display.waveshow(a, sr=sr,color="yellow")
librosa.display.waveshow(f, sr=sr,color="black")
plt.title('abeille/frelon')
plt.show()

# 3. Calcul et affichage du spectrogramme (Domaine fréquentiel)
A = librosa.amplitude_to_db(np.abs(librosa.stft(a)), ref=np.max)
F = librosa.amplitude_to_db(np.abs(librosa.stft(f)), ref=np.max)

plt.figure(figsize=(10, 4))
librosa.display.specshow(A, sr=sr, x_axis='time', y_axis='log')
plt.colorbar(format='%+2.0f dB')
plt.title('Spectrogramme en décibels')
plt.show()

plt.figure(figsize=(10, 4))
librosa.display.specshow(F, sr=sr, x_axis='time', y_axis='log')
plt.colorbar(format='%+2.0f dB')
plt.title('Spectrogramme en décibels')
plt.show()
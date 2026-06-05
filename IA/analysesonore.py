import librosa
import soundfile as sf
import librosa.display
import matplotlib.pyplot as plt
import numpy as np

n_fft = 8192 # on augmente la précision de l'analyse spectral
hop_length = 1024 #temps de décalage 

def affichage_audio(inten_sono,fe):
    plt.figure(figsize=(10, 4))
    librosa.display.waveshow(inten_sono, sr=fe,color="black")
    plt.title('intensité sonore')
    plt.show()
    return

def affichage_spectre_audio(inten_sono,fe):
    spectre = librosa.amplitude_to_db(np.abs(librosa.stft(inten_sono)), ref=np.max)
    plt.figure(figsize=(10, 4))
    librosa.display.specshow(spectre, sr=fe, x_axis='time', y_axis='log')
    plt.colorbar(format='%+2.0f dB')
    plt.title('Spectrogramme en décibels')
    plt.show()
    return

def affichage_spectre_audio_zoom(inten_sono,fe):
    D = librosa.stft(inten_sono, n_fft=n_fft, hop_length=hop_length)
    spectre  = librosa.amplitude_to_db(np.abs(D), ref=np.max)
    plt.figure(figsize=(12, 5))
    librosa.display.specshow(spectre , sr=fe, hop_length=hop_length, x_axis='time', y_axis='linear', cmap='magma')
    plt.colorbar(format='%+2.0f dB')
    plt.title('Spectrogramme Zoomé (0 - 1000 Hz) - Frelon près de la ruche')
    plt.ylim(50, 1000) 
    plt.ylabel('Fréquence (Hz)')
    plt.show()
    return

def valeur_moyenne(inten_sono,fe):
    matrice_stft = np.abs(librosa.stft(inten_sono, n_fft=n_fft))
    frequences = librosa.fft_frequencies(sr=fe, n_fft=n_fft)
    masque_basses_freq = np.where((frequences >= 100) & (frequences <= 300))[0] #filtre dans le tableau les basses fréquences
    matrice_frelon = matrice_stft[masque_basses_freq, :]
    frequences_frelon = frequences[masque_basses_freq]
    profil_frequentiel = np.mean(matrice_frelon, axis=1) # calcul la moyenne horizontalement car matrice en 2D
    plt.figure(figsize=(10, 4))
    plt.plot(frequences_frelon, profil_frequentiel, color='red', linewidth=2)
    plt.title('Profil Moyen des Fréquences ')
    plt.xlabel('Fréquence (Hz)')
    plt.ylabel('Amplitude Moyenne (Volume)')
    plt.grid(True)
    plt.show()
    return profil_frequentiel

def temps_moyen_presence(inten_sono, fe):
    matrice_stft = np.abs(librosa.stft(inten_sono, n_fft=n_fft, hop_length=hop_length))
    frequences = librosa.fft_frequencies(sr=fe, n_fft=n_fft)
    masque = np.where((frequences >= 100) & (frequences <= 175))[0]
    volume_frelon_temps = np.mean(matrice_stft[masque, :], axis=0)
    # 🌟 LA NOUVEAUTÉ EST ICI : LE LISSAGE
    # On crée une moyenne mobile sur 10 cases (soit environ 0.5 seconde)
    # Ça efface les micro-coupures et fusionne les attaques hachées
    taille_lissage = 10 
    volume_lisse = np.convolve(volume_frelon_temps, np.ones(taille_lissage)/taille_lissage, mode='same')
    # On calcule le seuil sur la courbe lissée (on peut baisser un peu à 1.15 pour être plus sensible)
    seuil = np.mean(volume_lisse) * 1.15
    plt.figure(figsize=(10, 4))
    plt.plot(volume_lisse, color='blue', label='Volume du Frelon (Lissé)')
    plt.axhline(y=seuil, color='red', linestyle='--', label='Seuil de Détection')
    plt.title('Diagnostic : Déclenchement du chronomètre')
    plt.xlabel('Temps (en "cases" de 46ms)')
    plt.ylabel('Amplitude (Volume)')
    plt.legend()
    plt.show()
    # On utilise volume_lisse au lieu de volume_frelon_temps
    presence = (volume_lisse > seuil).astype(int)
    # --- LE NOUVEAU CHRONOMÈTRE AVEC TOLÉRANCE ---
    durees_en_cases = []
    compteur_frelon = 0
    
    # On définit une tolérance de 22 cases (soit environ 1 seconde complète)
    tolerance = 22 
    compteur_absence = 0
    
    for instant in presence:
        if instant == 1:
            compteur_frelon += 1
            compteur_absence = 0 # Le frelon est là, on annule l'absence
        else:
            if compteur_frelon > 0:
                compteur_absence += 1
                
                # On ne coupe le chrono QUE si l'absence dépasse la tolérance
                if compteur_absence > tolerance:
                    # On retire le temps de tolérance qu'on a compté en trop
                    durees_en_cases.append(compteur_frelon - tolerance)
                    compteur_frelon = 0
                    compteur_absence = 0
                else:
                    # Le frelon a disparu, mais on tolère, on laisse tourner le chrono !
                    compteur_frelon += 1

    if compteur_frelon > tolerance:
        durees_en_cases.append(compteur_frelon - tolerance)
        
    # --- LA CONVERSION EN SECONDES (Identique) ---
    duree_d_une_case_secondes = hop_length / fe
    temps_en_secondes = [duree * duree_d_une_case_secondes for duree in durees_en_cases]
    
    # Filtre optionnel : On ignore les "attaques" de moins de 1 seconde (trop court pour être un frelon)
    temps_valides = [t for t in temps_en_secondes if t > 1.0]
    
    return temps_valides

def ia_detection_naive(list_point):
    sum=0
    seuil=200 # je ne sais pas encore quoi mettre 
    for points in list_point:
        for i in range (len(courbe_moy)):
            if points[0]==courbe_moy[i][0]:
                sum+=np.abs(courbe_moy[i][1]-points[1])
    if sum < seuil:
        return True # on rajoutera un activable comme appeler une focntion qui enleve le mode veille
    return False # on rajoutera un activable comme appeler une focntion qui enleve le mode veille 

def ia_detection(profil_actuel, profil_moyen_global):
    """
    Compare le profil audio en direct avec la signature du frelon.
    Retourne True si on est sûr à + de 80% que c'est un frelon.
    """
    score_similarite = np.corrcoef(profil_actuel, profil_moyen_global)[0, 1]
    seuil_confiance = 0.80 
    print(f"📊 Score de correspondance IA : {score_similarite * 100:.1f}%")
    if score_similarite > seuil_confiance:
        return True # rajouter un activable, il ya présence d'un frelon
    else:
        return False # rajouter un activable, il ya présence d'un frelon

chemin_audio_frelon_ruche1_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 1 (see Table 1).wav"
chemin_audio_frelon_ruche2_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 2 (see Table 1).wav"
chemin_audio_frelon_ruche3_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 3 (see Table 1).wav"
chemin_audio_frelon_ruche4_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 4 (see Table 1).wav"
chemin_audio_frelon_ruche5_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 5 (see Table 1).wav"
chemin_audio_frelon_ruche1_2 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 1 (see Table 2).wav"

list_donne = [chemin_audio_frelon_ruche1_1,chemin_audio_frelon_ruche2_1,chemin_audio_frelon_ruche3_1,chemin_audio_frelon_ruche4_1,chemin_audio_frelon_ruche5_1,chemin_audio_frelon_ruche1_2]
toutes_les_courbes = []
tous_les_temps = []

for chemin in list_donne:
    audio, sr = librosa.load(chemin, sr=22050)
    profil_actuel = valeur_moyenne(audio, sr)
    toutes_les_courbes.append(profil_actuel)
    tous_les_temps.append(np.mean(temps_moyen_presence(audio,sr)))

print(np.mean(tous_les_temps))

profil_moyen_global = np.mean(toutes_les_courbes, axis=0)

frequences = librosa.fft_frequencies(sr=22050, n_fft=n_fft)
masque_basses_freq = np.where((frequences >= 100) & (frequences <= 300))[0]
frequences_frelon = frequences[masque_basses_freq]

plt.figure(figsize=(10, 4))
plt.plot(frequences_frelon, profil_moyen_global, color='purple', linewidth=3)
plt.title('Signature Acoustique Globale du Frelon (Moyenne sur 7 vidéos)')
plt.xlabel('Fréquence (Hz)')
plt.ylabel('Amplitude Moyenne Globale')
plt.grid(True)
plt.show()

"""test de faire des montages audios pour tester notre algoryhtme de détection"""
# 1. Chargement des deux sons (à la même vitesse de 22050 Hz !)
ruche, sr = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/bruit_ruche.wav", sr=22050)
frelon, _ = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/frelon_asiatique.wav", sr=22050)

audio_mixe = ruche.copy() * 0.5 

seconde_attaque = 5
index_debut = seconde_attaque * sr
index_fin = index_debut + len(frelon)

# On vérifie que la ruche est assez longue pour accueillir le frelon
if index_fin <= len(audio_mixe):
    # On injecte le frelon en boostant son volume
    audio_mixe[index_debut:index_fin] += (frelon * 1.5)
else:
    print("⚠️ Attention : La piste de la ruche est trop courte pour cette attaque.")

sf.write("simulation_attaque.wav", audio_mixe, sr)

extrait_mix = audio_mixe[index_debut:index_fin]
extrait_ruche_seule = ruche[index_debut:index_fin]

# On abandonne la courbe violette (les 7 vidéos) pour ce test
profil_reference_absolue = valeur_moyenne(frelon, sr)

# Et on teste notre mix contre cette nouvelle référence
resultat_vrai = ia_detection(valeur_moyenne(extrait_mix, sr), profil_reference_absolue)
print("\n🎯 BILAN DU CRASH-TEST :")

# On vérifie explicitement si l'IA a répondu True (Ce qu'on espère pour le frelon)
print(f"L'IA a vu le frelon (Test 1) ? : {resultat_vrai == True}")
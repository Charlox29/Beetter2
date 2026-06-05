import numpy as np
import librosa
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import random
import tensorflow as tf
from keras import layers
from keras import models
from keras import optimizers
from keras.applications import MobileNet
from tensorflow.keras.applications.mobilenet import preprocess_input

ruche, sr = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/bruit_ruche.wav", sr=22050)
frelon1, _ = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/son_frelon_long_mais_moins_propre.wav", sr=22050)
frelon2, _ = librosa.load("C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/frelon.wav", sr=22050)

# X contiendra nos empreintes (les 13 nombres)
# y contiendra les réponses (0 = Ruche, 1 = Frelon)
X = [] 
Y = [] 

taille_fenetre = 3 * sr  # Fenêtre de 3 secondes
saut = 2 * sr            # On avance de 1 seconde à la fois

frelon = np.concatenate((frelon1, frelon2))

# Découpage mathématique instantané
blocs_ruche = librosa.util.frame(ruche, frame_length=taille_fenetre, hop_length=saut)
blocs_frelon = librosa.util.frame(frelon, frame_length=taille_fenetre, hop_length=saut)

for i in range(blocs_ruche.shape[1]):
    morceau = blocs_ruche[:, i]
    mfcc = librosa.feature.mfcc(y=morceau, sr=sr, n_mfcc=13)
    
    # L'astuce : on fait la moyenne sur l'axe du temps (axis=1)
    mfcc_moyen = np.mean(mfcc, axis=1) 
    
    X.append(mfcc_moyen)
    Y.append(0) # 0 = "Ce n'est pas un frelon"

for i in range(blocs_frelon.shape[1]):
    
    # 1. On prend notre bloc pur de frelon (2 secondes)
    morceau_frelon = blocs_frelon[:, i]
    
    # 2. On choisit un bloc de ruche AU HASARD dans notre grand fichier ruche
    # (Pour ne pas toujours avoir le même bruit de fond)
    index_ruche_au_hasard = random.randint(0, blocs_ruche.shape[1] - 1)
    morceau_ruche = blocs_ruche[:, index_ruche_au_hasard]
    
    # 3. L'ASTUCE : On tire un volume au hasard pour le frelon (entre 0.3 et 1.5)
    # 0.3 = Frelon lointain, 1.5 = Frelon très proche du micro
    volume_f = random.uniform(0.3, 1.5)
    volume_r = 0.5 # On garde la ruche à un niveau moyen constant
    
    # 4. LE MIXAGE MATHÉMATIQUE !
    mixage = (morceau_ruche * volume_r) + (morceau_frelon * volume_f)
    
    # 5. Extraction du MFCC sur le son mixé
    mfcc = librosa.feature.mfcc(y=mixage, sr=sr, n_mfcc=13)
    mfcc_moyen = np.mean(mfcc, axis=1)
    
    # 6. On ajoute au Dataset
    X.append(mfcc_moyen)
    Y.append(1)

# On convertit nos listes en tableaux Numpy pour l'IA
X = np.array(X)
Y = np.array(Y)

print(f"📊 Dataset prêt ! {len(X)} échantillons analysés (13 caractéristiques chacun).")


# 2. ENTRAÎNEMENT DE L'IA (Le Cerveau)

# On coupe nos données : 80% pour l'apprentissage, 20% pour l'examen final
X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2, random_state=42)

# On crée une forêt de 100 arbres de décision
modele = RandomForestClassifier(n_estimators=100, random_state=42)

# La ligne où la machine APPREND :
modele.fit(X_train, Y_train) 

# 3. LE VERDICT (L'Examen)

score = modele.score(X_test, Y_test)

print(f"🎯 Précision de l'IA : {score * 100:.2f}%")

# le but étant de passer sur une analyse spectral par consequent il nous faut travailler nos échantillons pour les etiqueter grâce àla metode précedente

chemin_audio_frelon_ruche1_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 1 (see Table 1).wav"
chemin_audio_frelon_ruche2_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 2 (see Table 1).wav"
chemin_audio_frelon_ruche3_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 3 (see Table 1).wav"
chemin_audio_frelon_ruche4_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 4 (see Table 1).wav"
chemin_audio_frelon_ruche5_1 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 5 (see Table 1).wav"
chemin_audio_frelon_ruche1_2 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 1 (see Table 2).wav"
chemin_audio_frelon_ruche2_2 ="C:/Users/simon/Desktop/Esiee/projet fin d'année/fichier sonore frelon asiatique/Video 2 (see Table 2).wav"

liste_chemin=[chemin_audio_frelon_ruche1_1,chemin_audio_frelon_ruche2_1,chemin_audio_frelon_ruche3_1,chemin_audio_frelon_ruche4_1,chemin_audio_frelon_ruche5_1,chemin_audio_frelon_ruche1_2,chemin_audio_frelon_ruche2_2]
liste_son=[]
blocs_son=[]

print("🚁 Lancement du Radar IA pour extraire les Spectrogrammes...")

# A contiendra nos images (Spectrogrammes)
# B contiendra les réponses (0 = Ruche, 1 = Frelon)
A = [] 
B = [] 

for i in range(len(liste_chemin)):
    print(f"Analyse de la vidéo {i+1}/{len(liste_chemin)}...")
    
    # CORRECTION 1 : On sépare bien l'audio de la fréquence (le petit '_')
    audio_courant, _ = librosa.load(liste_chemin[i], sr=22050)
    
    # On découpe
    blocs = librosa.util.frame(audio_courant, frame_length=taille_fenetre, hop_length=saut)
    
    for j in range(blocs.shape[1]):
        morceau = blocs[:, j]
        
        # --- 1. L'Avis du Random Forest (MFCC) ---
        mfcc = librosa.feature.mfcc(y=morceau, sr=sr, n_mfcc=13)
        mfcc_moyen = np.mean(mfcc, axis=1)
        probabilites = modele.predict_proba([mfcc_moyen])[0]
        
        # --- 2. La création de l'image (Spectrogramme) ---
        spectre = librosa.amplitude_to_db(np.abs(librosa.stft(morceau)), ref=np.max)
        
        # --- 3. Le Tri ---
        if probabilites[0] > 0.70: # 70% sûr que c'est une Ruche
            A.append(spectre)
            B.append(0)
        elif probabilites[1] > 0.70: # 70% sûr que c'est un Frelon
            A.append(spectre)
            B.append(1)

for v in range(1100):
        morceau = blocs_ruche[:, v]
        spectre = librosa.amplitude_to_db(np.abs(librosa.stft(morceau)), ref=np.max)
        A.append(spectre)
        B.append(0)

A = np.array(A)
B = np.array(B)

print(f"✅ Extraction terminée ! {len(A)} spectrogrammes ont été générés.")

c=0
for k in range (len(B)):
    if B[k]==0 :
        c+=1

print(f"nombre de 0 = {c},nombre de 1 = {len(B)-c}")

# On prépare le jeu de données pour le futur Réseau de Neurones
A_train, A_test, B_train, B_test = train_test_split(A, B, test_size=0.2, random_state=42)

# ==========================================
# 1. ADAPTATION DES TABLEAUX NUMPY POUR MOBILENET
# ==========================================
print("🎨 Transformation de vos tableaux NumPy en tenseurs RGB (128x128x3)...")

def formater_matrices_pour_mobilenet(tableau_spectres):
    """
    Prend un tableau NumPy de spectrogrammes bruts et le transforme
    en un bloc d'images carrées à 3 canaux compatible avec MobileNet.
    """
    images_formatees = []
    
    for spectre in tableau_spectres:
        # A. Normalisation entre 0 et 255 (car amplitude_to_db donne du négatif)
        spectre_min = spectre.min()
        spectre_max = spectre.max()
        if spectre_max - spectre_min > 0:
            spectre_normalise = (spectre - spectre_min) / (spectre_max - spectre_min) * 255.0
        else:
            spectre_normalise = spectre * 0.0
            
        # B. Ajout de la dimension de canal manquante -> (Hauteur, Largeur, 1)
        spectre_2d = spectre_normalise[..., np.newaxis]
        
        # C. Redimensionnement en 128x128 via TensorFlow
        spectre_resized = tf.image.resize(spectre_2d, [128, 128])
        
        # D. Conversion de niveaux de gris à RGB (copie de la matrice sur 3 canaux)
        spectre_rgb = tf.image.grayscale_to_rgb(spectre_resized)
        
        images_formatees.append(spectre_rgb.numpy())
        
    return np.array(images_formatees)

# On applique la transformation sur vos données de mémoire vive
# (A_train et A_test proviennent de votre split précédent)
A_train_ready = formater_matrices_pour_mobilenet(A_train)
A_test_ready = formater_matrices_pour_mobilenet(A_test)

# On applique le prétraitement officiel de MobileNet (normalisation interne)
A_train_ready = preprocess_input(A_train_ready)
A_test_ready = preprocess_input(A_test_ready)

print(f"Forme finale pour l'entraînement : {A_train_ready.shape}") # Doit afficher (Nb, 128, 128, 3)

# ==========================================
# 2. CONFIGURATION DU RÉSEAU DE NEURONES (CNN)
# ==========================================

# Base de convolution MobileNet pré-entraînée
conv_base = MobileNet(weights='imagenet', include_top=False, input_shape=(128, 128, 3), alpha=0.5)
conv_base.trainable = False

# Assemblage du modèle
model = models.Sequential()
model.add(conv_base)
model.add(layers.Flatten())
model.add(layers.Dense(256, activation='relu'))
model.add(layers.Dropout(0.5))

model.add(layers.Dense(1, activation='sigmoid'))

# !!! CORRECTION : loss='binary_crossentropy' (adapté au choix Ruche vs Frelon)
model.compile(loss='binary_crossentropy', 
              optimizer=optimizers.Adam(learning_rate=1e-5), 
              metrics=['acc'])

# ==========================================
# 3. ENTRAÎNEMENT PHASE 1 (Transfer Learning)
# ==========================================
print("\n--- PHASE 1 : Entraînement des couches supérieures ---")
# Remplacement des générateurs par vos variables NumPy directes !
history_1 = model.fit(
      A_train_ready, B_train,
      epochs=20,
      batch_size=32,
      validation_data=(A_test_ready, B_test),
      verbose=2)

# ==========================================
# 4. ENTRAÎNEMENT PHASE 2 (Fine-Tuning)
# ==========================================
print("\n--- PHASE 2 : Dégel partiel et Fine-Tuning de MobileNet ---")
conv_base.trainable = True

set_trainable = False
for layer in conv_base.layers:
    if layer.name == 'conv_dw_11':
        set_trainable = True
    if set_trainable:
        layer.trainable = True
    else:
        layer.trainable = False

# Re-compilation obligatoire après modification du gel des couches
model.compile(loss='binary_crossentropy', 
              optimizer=optimizers.Adam(learning_rate=1e-5), 
              metrics=['acc'])

history_2 = model.fit(
       A_train_ready, B_train,
       epochs=20,
       batch_size=32,
       validation_data=(A_test_ready, B_test),
       verbose=1)


test_loss, test_acc = model.evaluate(A_test_ready, B_test)
print('\n=======================================')
print('🎯 PRECISION FINALE SUR LE TEST SET : {:2.2f}%'.format(test_acc*100))
print('=======================================\n')

def tester_nouveau_son(chemin_fichier, modele_entraine):
    """
    Prend un fichier audio (idéalement de 3 secondes), le transforme en image 
    compatible avec MobileNet, et demande l'avis de l'IA.
    """
    print(f"\n🎧 Analyse de l'échantillon : {chemin_fichier}...")
    audio, sr = librosa.load(chemin_fichier, sr=22050)
    
    # 2. Création du Spectrogramme (Mathématiques brutes)
    spectre = librosa.amplitude_to_db(np.abs(librosa.stft(audio)), ref=np.max)
    
    # 3. Formatage pour MobileNet (Le même pipeline que l'entraînement !)
    # A. Normalisation 0-255
    spectre_min = spectre.min()
    spectre_max = spectre.max()
    if spectre_max - spectre_min > 0:
        spectre_norm = (spectre - spectre_min) / (spectre_max - spectre_min) * 255.0
    else:
        spectre_norm = spectre * 0.0
        
    # B. Ajout du canal et redimensionnement
    spectre_2d = spectre_norm[..., np.newaxis]
    spectre_resized = tf.image.resize(spectre_2d, [128, 128])
    spectre_rgb = tf.image.grayscale_to_rgb(spectre_resized)
    
    image_finale = np.expand_dims(spectre_rgb.numpy(), axis=0)
    
    # D. Prétraitement MobileNet (Normalisation entre -1 et 1)
    image_finale = preprocess_input(image_finale)
    prediction = modele_entraine.predict(image_finale)[0][0]
    if prediction >= 0.5:
        print(f"   Confiance que c'est un frelon : {prediction * 100:.1f}%")
    else:
        print(f"   Confiance que c'est une ruche : {(1 - prediction) * 100:.1f}%")
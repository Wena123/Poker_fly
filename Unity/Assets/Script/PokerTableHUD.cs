using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// World-space billboard HUD next to the poker board:
/// live POT amount + up to five real card pictures, loaded from Resources/cards/.
/// No text like AH/KD is displayed for the board cards.
/// </summary>
public class PokerTableHUD : MonoBehaviour
{
    [Header("Placement")]
    [Tooltip("Optional. Usually BOARD. Automatically locates BOARD, then PotArchorn/PotAnchor.")]
    public Transform hudAnchor;
    public Camera targetCamera;
    [Tooltip("World-space offset from BOARD/PotAnchor. Increase Y to raise the HUD.")]
    public Vector3 worldOffset = new Vector3(0f, 0.20f, 0f);
    [Tooltip("Scale of world-space panel. Smaller number = smaller cards.")]
    [Range(0.0005f, 0.008f)]
    public float canvasScale = 0.0017f;

    [Tooltip("Optional manual 180 degree flip if your scene uses a nonstandard UI orientation.")]
    public bool flipHud180 = false;

    [Header("Card display")]
    public float boardCardSpacing = 62f;
    public bool showPot = true;
    public bool showBoardPictures = true;

    private GameObject canvasRoot;
    private RectTransform canvasRect;
    private TMP_Text potText;
    private readonly RawImage[] boardImages = new RawImage[5];
    private readonly string[] shownCardCodes = { "", "", "", "", "" };
    private readonly string[] boardCodes = { "", "", "", "", "" };
    private int currentPot = 0;

    // More than one PokerTableHUD can exist after manual setup + automatic setup.
    // Only one instance is allowed to render the POT / board card canvas.
    private static PokerTableHUD primaryHUD;
    private bool duplicateWarningShown;

    /// <summary>
    /// Finds the one HUD which should render the pot and cards.
    /// An explicitly created TableHUD takes precedence over an auto-added one.
    /// </summary>
    public static PokerTableHUD GetPrimaryHUD()
    {
        PokerTableHUD[] all = FindObjectsByType<PokerTableHUD>(
            FindObjectsInactive.Include,
            FindObjectsSortMode.None
        );

        PokerTableHUD best = null;
        int bestScore = int.MinValue;
        int bestId = int.MaxValue;

        foreach (PokerTableHUD hud in all)
        {
            if (hud == null || !hud.isActiveAndEnabled || !hud.gameObject.scene.IsValid())
                continue;

            int score = 0;
            string objectName = hud.gameObject.name;

            // The hand-created TableHUD is preferred over a HUD automatically
            // added to the PokerReceiver GameObject.
            if (objectName == "TableHUD" || objectName == "PokerTableHUD")
                score += 100;

            if (hud.hudAnchor != null)
                score += 20;

            if (hud.GetComponent<PokerReceiver>() == null)
                score += 10;

            int id = hud.GetInstanceID();
            if (best == null || score > bestScore || (score == bestScore && id < bestId))
            {
                best = hud;
                bestScore = score;
                bestId = id;
            }
        }

        primaryHUD = best;
        return best;
    }

    private void OnEnable()
    {
        GetPrimaryHUD();
    }

    private bool IsPrimary()
    {
        if (primaryHUD == null || !primaryHUD.isActiveAndEnabled)
            GetPrimaryHUD();
        return primaryHUD == this;
    }

    private void RemoveDuplicateCanvas()
    {
        if (canvasRoot != null)
        {
            Destroy(canvasRoot);
            canvasRoot = null;
            canvasRect = null;
            potText = null;
            for (int i = 0; i < 5; i++)
                boardImages[i] = null;
        }

        if (!duplicateWarningShown)
        {
            duplicateWarningShown = true;
            Debug.LogWarning("[PokerTableHUD] Duplicate HUD on '" + gameObject.name +
                "' will NOT show another POT. Active HUD: '" +
                (primaryHUD != null ? primaryHUD.gameObject.name : "none") + "'.");
        }
    }

    private void Awake()
    {
        TryFindAnchor();
        if (targetCamera == null) targetCamera = Camera.main;
    }

    private void Start()
    {
        GetPrimaryHUD();
        if (!IsPrimary())
        {
            RemoveDuplicateCanvas();
            return;
        }

        BuildCanvas();
        RefreshPot();
        RefreshBoard();
    }

    private void LateUpdate()
    {
        if (!IsPrimary())
        {
            RemoveDuplicateCanvas();
            return;
        }

        // An alternate HUD might have been active in an earlier frame.
        if (canvasRoot == null)
        {
            BuildCanvas();
            RefreshPot();
            RefreshBoard();
        }
        if (canvasRoot == null) return;
        TryFindAnchor();
        if (targetCamera == null) targetCamera = Camera.main;
        canvasRect.localScale = Vector3.one * Mathf.Max(0.0001f, canvasScale);
        canvasRect.position = (hudAnchor != null ? hudAnchor.position : transform.position) + worldOffset;
        if (targetCamera != null)
        {
            Vector3 toCamera = targetCamera.transform.position - canvasRect.position;
            if (toCamera.sqrMagnitude > 0.0001f)
            {
                // A world-space Canvas shows its FRONT on local -Z.
                // The old version faced +Z toward the camera, making POT
                // and the card images appear mirrored/backwards.
                canvasRect.rotation = Quaternion.LookRotation(-toCamera, Vector3.up);
                if (flipHud180)
                    canvasRect.Rotate(0f, 180f, 0f, Space.Self);
            }
        }
        for (int i = 0; i < 5; i++)
        {
            if (boardImages[i] != null)
                boardImages[i].rectTransform.anchoredPosition = new Vector2((i - 2) * boardCardSpacing, -35f);
        }
    }

    private void OnDisable()
    {
        if (primaryHUD == this)
        {
            primaryHUD = null;
        }
        RemoveOwnedCanvas();
    }

    private void OnDestroy()
    {
        if (primaryHUD == this)
            primaryHUD = null;
        RemoveOwnedCanvas();
    }

    private void RemoveOwnedCanvas()
    {
        if (canvasRoot == null)
            return;

        Destroy(canvasRoot);
        canvasRoot = null;
        canvasRect = null;
        potText = null;
        for (int i = 0; i < boardImages.Length; i++)
            boardImages[i] = null;
    }

    private void TryFindAnchor()
    {
        if (hudAnchor != null) return;
        GameObject obj = GameObject.Find("BOARD");
        if (obj == null) obj = GameObject.Find("PotArchorn");
        if (obj == null) obj = GameObject.Find("PotAnchor");
        if (obj != null) hudAnchor = obj.transform;
    }

    public void NewHand()
    {
        PokerTableHUD primary = GetPrimaryHUD();
        if (primary != null && primary != this)
        {
            primary.NewHand();
            return;
        }
        currentPot = 0;
        for (int i = 0; i < 5; i++) boardCodes[i] = "";
        RefreshPot();
        RefreshBoard();
    }

    public void SetPot(int amount)
    {
        PokerTableHUD primary = GetPrimaryHUD();
        if (primary != null && primary != this)
        {
            primary.SetPot(amount);
            return;
        }
        currentPot = Mathf.Max(0, amount);
        RefreshPot();
    }

    public void SetBoard(string[] cards)
    {
        PokerTableHUD primary = GetPrimaryHUD();
        if (primary != null && primary != this)
        {
            primary.SetBoard(cards);
            return;
        }
        for (int i = 0; i < 5; i++)
            boardCodes[i] = cards != null && i < cards.Length && !string.IsNullOrWhiteSpace(cards[i])
                ? cards[i].Trim().ToUpperInvariant() : "";
        RefreshBoard();
    }

    private void BuildCanvas()
    {
        if (!IsPrimary())
        {
            RemoveOwnedCanvas();
            return;
        }
        if (canvasRoot != null) return;

        canvasRoot = new GameObject("PokerTable_PotAndBoardHUD_Auto",
            typeof(RectTransform), typeof(Canvas));
        canvasRect = canvasRoot.GetComponent<RectTransform>();
        canvasRect.sizeDelta = new Vector2(410, 185);
        Canvas canvas = canvasRoot.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;
        canvas.overrideSorting = true;
        canvas.sortingOrder = 160;

        GameObject potObject = new GameObject("PotAmount", typeof(RectTransform), typeof(TextMeshProUGUI));
        potObject.transform.SetParent(canvasRoot.transform, false);
        RectTransform potRect = potObject.GetComponent<RectTransform>();
        potRect.anchorMin = potRect.anchorMax = new Vector2(0.5f, 0.5f);
        potRect.sizeDelta = new Vector2(405f, 72f);
        potRect.anchoredPosition = new Vector2(0f, 52f);
        TextMeshProUGUI tmp = potObject.GetComponent<TextMeshProUGUI>();
        tmp.fontSize = 40f;
        tmp.alignment = TextAlignmentOptions.Center;
        tmp.color = Color.white;
        tmp.enableWordWrapping = false;
        tmp.raycastTarget = false;
        potText = tmp;

        for (int i = 0; i < 5; i++)
        {
            GameObject imageObject = new GameObject("BoardCard" + (i + 1),
                typeof(RectTransform), typeof(RawImage));
            imageObject.transform.SetParent(canvasRoot.transform, false);
            RectTransform rect = imageObject.GetComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.sizeDelta = new Vector2(56f, 81f);
            rect.anchoredPosition = new Vector2((i - 2) * boardCardSpacing, -35f);
            RawImage raw = imageObject.GetComponent<RawImage>();
            raw.raycastTarget = false;
            raw.gameObject.SetActive(false);
            boardImages[i] = raw;
        }
    }

    private void RefreshPot()
    {
        BuildCanvas();
        if (potText == null) return;
        potText.gameObject.SetActive(showPot);
        potText.text = "POT: " + currentPot;
    }

    private void RefreshBoard()
    {
        BuildCanvas();
        for (int i = 0; i < 5; i++)
        {
            if (boardImages[i] == null) continue;
            string code = boardCodes[i];
            bool visible = showBoardPictures && code.Length > 0;
            if (!visible)
            {
                boardImages[i].gameObject.SetActive(false);
                continue;
            }
            if (shownCardCodes[i] != code)
            {
                shownCardCodes[i] = code;
                boardImages[i].texture = Resources.Load<Texture2D>("cards/" + code);
                if (boardImages[i].texture == null)
                    Debug.LogWarning("[PokerTableHUD] Missing PNG: Assets/Resources/cards/" + code + ".png");
            }
            boardImages[i].gameObject.SetActive(boardImages[i].texture != null);
        }
    }
}

using UnityEngine;

public class AnchorHold : MonoBehaviour
{
    [Header("Anchors")]
    public Transform handAnchor;
    public Transform betAnchor;

    [Header("Offset w rece")]
    public Vector3 handPositionOffset = Vector3.zero;
    public Vector3 handRotationOffset = Vector3.zero;

    [Header("Smooth follow")]
    public float followSpeed = 25f;
    public float rotationSpeed = 25f;

    private Transform currentChip;
    private Rigidbody currentRb;

    private bool holdingChip = false;


    // =====================================================
    // POKER RECEIVER PODAJE TUTAJ ZETON
    // =====================================================

    public void SetChip(GameObject chip)
    {
        if (chip == null)
        {
            Debug.LogWarning("SetChip dostal NULL!");
            return;
        }

        currentChip = chip.transform;
        currentRb = chip.GetComponent<Rigidbody>();

        Debug.Log("AnchorHold dostal zeton: " + chip.name);
    }


    // =====================================================
    // ANIMATION EVENT - LAPIE ZETON
    // =====================================================

    public void PickUp()
    {
        if (currentChip == null)
        {
            Debug.LogWarning("PickUp: PokerReceiver nie podal jeszcze zetonu!");
            return;
        }

        if (handAnchor == null)
        {
            Debug.LogError("Brak HandAnchor!");
            return;
        }

        if (currentRb != null)
        {
            currentRb.linearVelocity = Vector3.zero;
            currentRb.angularVelocity = Vector3.zero;

            currentRb.isKinematic = true;
            currentRb.useGravity = false;
        }

        holdingChip = true;

        Debug.Log("PICKUP: " + currentChip.name);
    }


    // =====================================================
    // SLEDZENIE REKI
    // =====================================================

    private void LateUpdate()
    {
        if (!holdingChip || currentChip == null || handAnchor == null)
            return;

        Vector3 targetPosition =
            handAnchor.TransformPoint(handPositionOffset);

        Quaternion targetRotation =
            handAnchor.rotation *
            Quaternion.Euler(handRotationOffset);


        // NIE teleportujemy od razu.
        // Zeton plynnie dogania reke.

        currentChip.position = Vector3.Lerp(
            currentChip.position,
            targetPosition,
            1f - Mathf.Exp(-followSpeed * Time.deltaTime)
        );

        currentChip.rotation = Quaternion.Slerp(
            currentChip.rotation,
            targetRotation,
            1f - Mathf.Exp(-rotationSpeed * Time.deltaTime)
        );
    }


    // =====================================================
    // ANIMATION EVENT - PUSZCZA
    // =====================================================

    public void ReleaseToBet()
    {
        if (currentChip == null)
        {
            Debug.LogWarning("ReleaseToBet: brak zetonu!");
            return;
        }

        if (betAnchor == null)
        {
            Debug.LogError("Brak BetAnchor!");
            return;
        }

        holdingChip = false;

        currentChip.position = betAnchor.position;
        currentChip.rotation = betAnchor.rotation;

        if (currentRb != null)
        {
            currentRb.linearVelocity = Vector3.zero;
            currentRb.angularVelocity = Vector3.zero;

            currentRb.isKinematic = true;
            currentRb.useGravity = false;
        }

        Debug.Log("RELEASE -> BET: " + currentChip.name);

        currentChip = null;
        currentRb = null;
    }
}
using System.Collections;
using UnityEngine;

public class PokerRaiseAnimation : MonoBehaviour
{

    [Header("Hands")]
    public Transform hands;
    public Transform idleAnchor;
    public Transform chipAnchor;
    public Transform betAnchor;

    [Header("Visual chips")]
    public GameObject chipBundlePrefab;

    [Header("Speed")]
    public float moveTime = 0.35f;
    public float pauseTime = 0.12f;

    public void PlayRaise(int raiseAmount)
    {
        StartCoroutine(RaiseAnimation(raiseAmount));
    }

    private IEnumerator RaiseAnimation(int raiseAmount)
    {
        // 1. Reach for chips
        yield return MoveTo(hands, chipAnchor.position, chipAnchor.rotation);

        yield return new WaitForSeconds(pauseTime);

        // 2. Create chips in the hand
        GameObject chips = Instantiate(
            chipBundlePrefab,
            chipAnchor.position,
            chipAnchor.rotation
        );

        chips.transform.SetParent(hands, true);

        // 3. Move hand + chips to BetAnchor
        yield return MoveTo(hands, betAnchor.position, betAnchor.rotation);

        // 4. Drop chips
        chips.transform.SetParent(null, true);

        chips.transform.position = betAnchor.position;

        yield return new WaitForSeconds(pauseTime);

        // 5. Hands go back
        yield return MoveTo(
            hands,
            idleAnchor.position,
            idleAnchor.rotation
        );
    }

    private IEnumerator MoveTo(
        Transform obj,
        Vector3 targetPosition,
        Quaternion targetRotation
    )
    {
        Vector3 startPosition = obj.position;
        Quaternion startRotation = obj.rotation;

        float timer = 0f;

        while (timer < moveTime)
        {
            timer += Time.deltaTime;

            float t = Mathf.Clamp01(timer / moveTime);

            // smoother movement
            t = t * t * (3f - 2f * t);

            obj.position = Vector3.Lerp(
                startPosition,
                targetPosition,
                t
            );

            obj.rotation = Quaternion.Slerp(
                startRotation,
                targetRotation,
                t
            );

            yield return null;
        }

        obj.position = targetPosition;
        obj.rotation = targetRotation;
    }
}
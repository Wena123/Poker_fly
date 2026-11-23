using UnityEngine;
using UnityEngine.InputSystem;

public class RaiseTest : MonoBehaviour
{
    public PokerRaiseAnimation player1Raise;

    void Update()
    {
        if (Keyboard.current != null &&
            Keyboard.current.rKey.wasPressedThisFrame)
        {
            Debug.Log("R pressed - playing raise animation");

            player1Raise.PlayRaise(150);
        }
    }
}